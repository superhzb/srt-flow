from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from srt_mlx_worker import api, llm


def test_public_api_all_names_are_resolvable() -> None:
    for name in api.__all__:
        assert hasattr(api, name), f"{name} in __all__ but not defined in api"


def test_create_app_exposes_expected_endpoints() -> None:
    app = api.create_app()

    assert app.title == "SRT MLX Worker"
    assert _route_paths(app.routes) >= {"/health", "/languages", "/translate", "/translate/stream"}


@pytest.mark.parametrize("field", ["model_path"])
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
    def raise_unavailable(_config: object) -> None:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("srt_mlx_worker.llm.ensure_model_available", raise_unavailable)
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
    config = api.TranslationConfig()

    def raise_attribute_error(_module_name: str) -> object:
        raise AttributeError("broken dependency import")

    monkeypatch.setattr(llm.importlib, "import_module", raise_attribute_error)

    with pytest.raises(RuntimeError, match="Unable to load MLX dependency"):
        llm.ensure_model_available(config)


def _route_paths(routes: Sequence[object]) -> set[str]:
    paths: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
    return paths


def _config(tmp_path: Path) -> api.TranslationConfig:
    languages_path = tmp_path / "languages.yaml"
    languages_path.write_text(
        """
languages:
  - lang_code: fr
    lang_name: 法语
    example: Bonjour
  - lang_code: zh
    lang_name: 中文
    example: 你好
""",
        encoding="utf-8",
    )
    return api.TranslationConfig(
        languages_path=str(languages_path),
        max_retries=0,
        retry_delay=0,
    )
