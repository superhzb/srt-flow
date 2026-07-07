from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from srt_mlx_worker import api, llm

public_names = api.__all__


def test_public_api_all_names_are_resolvable() -> None:
    for name in public_names:
        assert hasattr(api, name), f"{name} in __all__ but not defined in api"


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
    client = TestClient(api.create_app(_config(tmp_path)))

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
    client = TestClient(api.create_app(_config(tmp_path)))

    response = client.post("/translate", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    [
        "model_path",
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
def test_request_rejects_worker_config_fields(tmp_path: Path, field: str) -> None:
    client = TestClient(api.create_app(_config(tmp_path)))

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


def test_model_unavailable_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_unavailable(_model_path: str) -> None:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("srt_mlx_worker.translator.ensure_model_available", raise_unavailable)
    client = TestClient(api.create_app(_config(tmp_path)))

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


def test_mlx_import_failure_returns_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_attribute_error(_module_name: str) -> object:
        raise AttributeError("broken dependency import")

    monkeypatch.setattr(llm.importlib, "import_module", raise_attribute_error)

    with pytest.raises(RuntimeError, match="Unable to load MLX dependency"):
        llm.ensure_model_available("test-model")


def test_languages_returns_code_name_list(tmp_path: Path) -> None:
    client = TestClient(api.create_app(_config(tmp_path, extra_langs=True)))

    response = client.get("/languages")

    assert response.status_code == 200
    assert response.json() == {
        "languages": [
            {"code": "es", "name": "español"},
            {"code": "fr", "name": "法语"},
            {"code": "zh", "name": "中文"},
        ]
    }


def test_create_app_exposes_expected_endpoints() -> None:
    app = api.create_app()

    assert app.title == "SRT MLX Worker"
    assert _route_paths(app.routes) >= {"/health", "/languages", "/translate"}


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
        template_path=str(Path(__file__).parents[1] / "src/srt_mlx_worker/template.txt"),
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
