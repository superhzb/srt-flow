import json
import os
import subprocess
import sys
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pkg_translator import api


def test_public_api_all_names_are_resolvable() -> None:
    for name in api.__all__:
        assert hasattr(api, name), f"{name} in __all__ but not defined in api"


def test_default_resources_load_from_package() -> None:
    config = api.TranslationConfig()

    assert Path(config.languages_path).name == "languages.yaml"
    assert Path(config.template_path).name == "template.txt"
    assert api.available_languages(config.languages_path)
    assert "{segments}" in api.load_template(config.template_path)


def test_wheel_installs_package_resources(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    target_dir = tmp_path / "site"

    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    wheel = next(dist_dir.glob("pkg_translator-*.whl"))
    with zipfile.ZipFile(wheel) as wheel_file:
        wheel_file.extractall(target_dir)

    code = """
from pkg_translator import api

config = api.TranslationConfig()
assert str(config.languages_path).startswith({target!r})
assert str(config.template_path).startswith({target!r})
assert api.available_languages(config.languages_path)
assert "{{segments}}" in api.load_template(config.template_path)
""".format(target=str(target_dir))
    env = {**os.environ, "PYTHONPATH": str(target_dir)}
    subprocess.run([sys.executable, "-c", code], check=True, cwd=tmp_path, env=env)


def test_translate_segments_single_target_preserves_order(tmp_path: Path) -> None:
    config = _config(tmp_path)

    targets, segments = api.translate_segments(
        "fr",
        ["zh"],
        [{"id": 2, "fr": "Au revoir"}, {"id": 1, "fr": "Bonjour"}],
        config=config,
        translator=_fake_translator,
    )

    assert targets == ["zh"]
    assert segments == [
        {"id": 2, "fr": "Au revoir", "zh": "再见"},
        {"id": 1, "fr": "Bonjour", "zh": "你好"},
    ]


def test_translate_segments_multi_target_flat_output(tmp_path: Path) -> None:
    config = _config(tmp_path, extra_langs=True)

    targets, segments = api.translate_segments(
        "fr",
        ["zh", "es", "zh"],
        [{"id": 1, "fr": "Bonjour"}],
        config=config,
        translator=_fake_translator,
    )

    assert targets == ["zh", "es"]
    assert segments == [{"id": 1, "fr": "Bonjour", "zh": "你好", "es": "Hola"}]


def test_unsupported_target_is_skipped(tmp_path: Path) -> None:
    config = _config(tmp_path)

    targets, segments = api.translate_segments(
        "fr",
        ["es", "zh"],
        [{"id": 1, "fr": "Bonjour"}],
        config=config,
        translator=_fake_translator,
    )

    assert targets == ["zh"]
    assert segments == [{"id": 1, "fr": "Bonjour", "zh": "你好"}]


def test_all_unsupported_targets_raise_400_in_route(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/translate",
        json={
            "source_lang": "fr",
            "targets": ["es"],
            "segments": [{"id": 1, "fr": "Bonjour"}],
        },
    )

    assert response.status_code == 400


def test_segment_validation_failure_drops_only_that_target_key(tmp_path: Path) -> None:
    config = _config(tmp_path, batch_size=2)

    targets, segments = api.translate_segments(
        "fr",
        ["zh"],
        [{"id": 1, "fr": "Bonjour"}, {"id": 2, "fr": "FAIL"}],
        config=config,
        translator=_fake_translator_with_one_bad_segment,
    )

    assert targets == ["zh"]
    assert segments == [
        {"id": 1, "fr": "Bonjour", "zh": "你好"},
        {"id": 2, "fr": "FAIL"},
    ]


def test_target_remains_attempted_when_every_segment_fails(tmp_path: Path) -> None:
    config = _config(tmp_path, batch_size=2)

    targets, segments = api.translate_segments(
        "fr",
        ["zh"],
        [{"id": 1, "fr": "FAIL"}, {"id": 2, "fr": "FAIL"}],
        config=config,
        translator=lambda _prompt, _config: "[]",
    )

    assert targets == ["zh"]
    assert segments == [{"id": 1, "fr": "FAIL"}, {"id": 2, "fr": "FAIL"}]


@pytest.mark.parametrize(
    "payload",
    [
        {"source_lang": "fr", "targets": [], "segments": [{"id": 1, "fr": "Bonjour"}]},
        {"source_lang": "fr", "targets": ["zh"], "segments": []},
        {
            "source_lang": "fr",
            "targets": ["zh"],
            "segments": [{"id": 1, "fr": "Bonjour"}, {"id": 1, "fr": "Salut"}],
        },
        {"source_lang": "fr", "targets": ["zh"], "segments": [{"id": 1}]},
        {"source_lang": "fr", "targets": ["zh"], "segments": [{"id": 1, "fr": "x", "zh": "y"}]},
        {"source_lang": "fr", "targets": ["zh"], "segments": [{"id": True, "fr": "Bonjour"}]},
    ],
)
def test_malformed_request_shape_returns_422(tmp_path: Path, payload: dict[str, object]) -> None:
    client = _client(tmp_path)

    response = client.post("/translate", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    [
        "template_path",
        "languages_path",
        "batch_size",
        "max_tokens",
        "temperature",
        "max_retries",
        "retry_delay",
        "context_window",
    ],
)
def test_request_rejects_shared_config_fields(tmp_path: Path, field: str) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/translate",
        json={
            "source_lang": "fr",
            "targets": ["zh"],
            "segments": [{"id": 1, "fr": "Bonjour"}],
            field: 1,
        },
    )

    assert response.status_code == 422


def test_model_unavailable_returns_503(tmp_path: Path) -> None:
    client = TestClient(
        api.create_app(
            _config(tmp_path),
            backend=_UnavailableBackend(),
            title="Shared Test Worker",
        )
    )

    response = client.post(
        "/translate",
        json={
            "source_lang": "fr",
            "targets": ["zh"],
            "segments": [{"id": 1, "fr": "Bonjour"}],
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "model unavailable"


def test_languages_returns_code_name_list(tmp_path: Path) -> None:
    client = _client(tmp_path, extra_langs=True)

    response = client.get("/languages")

    assert response.status_code == 200
    assert response.json() == {
        "languages": [
            {"code": "es", "name": "español"},
            {"code": "fr", "name": "法语"},
            {"code": "zh", "name": "中文"},
        ]
    }


def test_create_app_exposes_expected_endpoints(tmp_path: Path) -> None:
    app = api.create_app(_config(tmp_path), backend=_FakeBackend(_fake_translator), title="Core")

    assert app.title == "Core"
    assert _route_paths(app.routes) >= {"/health", "/languages", "/translate", "/translate/stream"}


def test_translate_stream_emits_progress_then_result(tmp_path: Path) -> None:
    progress_calls: list[api.BatchProgress] = []

    def fake_translate(
        source_lang: str,
        targets: list[str],
        segments: list[dict[str, object]],
        config: api.TranslationConfig | None,
        translator: object | None,
        on_progress: api.ProgressCallback | None,
        backend: api.LLMBackend | None,
    ) -> tuple[list[str], list[dict[str, object]]]:
        assert source_lang == "fr"
        assert targets == ["zh"]
        assert segments == [{"id": 1, "fr": "Bonjour"}]
        assert config is not None
        assert translator is None
        assert backend is not None
        assert on_progress is not None
        for batch_index in range(2):
            progress_calls.append(
                api.BatchProgress(
                    target="zh",
                    target_index=0,
                    target_total=1,
                    batch_index=batch_index,
                    batch_total=2,
                )
            )
            on_progress(progress_calls[-1])
        return ["zh"], [{"id": 1, "fr": "Bonjour", "zh": "你好"}]

    client = TestClient(
        api.create_app(
            _config(tmp_path),
            backend=_FakeBackend(_fake_translator),
            title="Shared Test Worker",
            translate_func=fake_translate,
        )
    )

    with client.stream(
        "POST",
        "/translate/stream",
        json={
            "source_lang": "fr",
            "targets": ["zh"],
            "segments": [{"id": 1, "fr": "Bonjour"}],
        },
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    progress = [e for e in events if e["event"] == "progress"]
    results = [e for e in events if e["event"] == "result"]
    errors = [e for e in events if e["event"] == "error"]
    assert errors == []
    assert len(progress) == 2
    assert progress[0] == {
        "event": "progress",
        "target": "zh",
        "target_index": 0,
        "target_total": 1,
        "batch_index": 0,
        "batch_total": 2,
    }
    assert len(results) == 1
    assert results[0]["source_lang"] == "fr"
    assert results[0]["targets"] == ["zh"]
    assert results[0]["segments"] == [{"id": 1, "fr": "Bonjour", "zh": "你好"}]


def test_translate_stream_emits_error_on_translator_failure(tmp_path: Path) -> None:
    def fake_translate(
        *_args: object, **_kwargs: object
    ) -> tuple[list[str], list[dict[str, object]]]:
        raise ValueError("No requested target is a supported language")

    client = TestClient(
        api.create_app(
            _config(tmp_path),
            backend=_FakeBackend(_fake_translator),
            title="Shared Test Worker",
            translate_func=fake_translate,
        )
    )

    with client.stream(
        "POST",
        "/translate/stream",
        json={
            "source_lang": "fr",
            "targets": ["zh"],
            "segments": [{"id": 1, "fr": "Bonjour"}],
        },
    ) as response:
        assert response.status_code == 200
        events = [json.loads(line) for line in response.iter_lines() if line]

    assert [e["event"] for e in events] == ["error"]
    assert "supported language" in events[0]["detail"]


def test_translate_stream_rejects_malformed_body(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = client.post(
        "/translate/stream",
        json={"source_lang": "fr", "targets": [], "segments": [{"id": 1, "fr": "x"}]},
    )

    assert response.status_code == 422


class _FakeBackend:
    def __init__(self, generate: Callable[[str, api.TranslationConfig], str]) -> None:
        self._generate = generate

    def ensure_model_available(self, config: api.TranslationConfig) -> None:
        _ = config
        return None

    def generate_text(self, prompt: str, config: api.TranslationConfig) -> str:
        return self._generate(prompt, config)


class _UnavailableBackend:
    def ensure_model_available(self, config: api.TranslationConfig) -> None:
        _ = config
        raise RuntimeError("model unavailable")

    def generate_text(self, prompt: str, config: api.TranslationConfig) -> str:
        _ = (prompt, config)
        raise AssertionError("generate_text should not be called")


def _client(tmp_path: Path, *, extra_langs: bool = False) -> TestClient:
    return TestClient(
        api.create_app(
            _config(tmp_path, extra_langs=extra_langs),
            backend=_FakeBackend(_fake_translator),
            title="Shared Test Worker",
        )
    )


def _route_paths(routes: Sequence[object]) -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
    return paths


def _config(
    tmp_path: Path,
    *,
    extra_langs: bool = False,
    batch_size: int = 10,
) -> api.TranslationConfig:
    languages_path = tmp_path / "languages.yaml"
    lang_yaml = """
languages:
  - lang_code: fr
    lang_name: 法语
    example: Bonjour
  - lang_code: zh
    lang_name: 中文
    example: 你好
"""
    if extra_langs:
        lang_yaml += """
  - lang_code: es
    lang_name: español
    example: Hola
"""
    languages_path.write_text(lang_yaml, encoding="utf-8")
    return api.TranslationConfig(
        languages_path=str(languages_path),
        batch_size=batch_size,
        max_retries=0,
        retry_delay=0,
    )


def _fake_translator(prompt: str, config: api.TranslationConfig) -> str:
    assert config.max_retries == 0
    if '"es"' in prompt:
        return '[{"id": 1, "es": "Hola"}]'
    if "Au revoir" in prompt:
        return '[{"id": 2, "zh": "再见"}, {"id": 1, "zh": "你好"}]'
    return '[{"id": 1, "zh": "你好"}]'


def _fake_translator_with_one_bad_segment(prompt: str, _config: api.TranslationConfig) -> str:
    if "FAIL" in prompt and "Bonjour" in prompt:
        return "[]"
    if "FAIL" in prompt:
        return '[{"id": 2, "zh": ""}]'
    return '[{"id": 1, "zh": "你好"}]'
