import pytest
from pkg_llm_backend.api import BackendResolutionError, load_backends


def test_load_backends_default_enables_mlx_and_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_BACKENDS", raising=False)
    monkeypatch.delenv("MLX_PLATFORM_BASE_URL", raising=False)

    backends = load_backends()

    assert set(backends) == {"mlx", "cloud"}
    assert backends["mlx"].project == "srt-flow"
    assert backends["mlx"].verify_model_alias is True
    assert backends["cloud"].api_key_env == "DEEPSEEK_API_KEY"
    assert backends["cloud"].extra_body == {"thinking": {"type": "disabled"}}
    assert backends["cloud"].verify_model_alias is False


def test_load_backends_cloud_only() -> None:
    backends = load_backends("cloud")

    assert set(backends) == {"cloud"}


def test_load_backends_strips_and_skips_empty_tokens() -> None:
    backends = load_backends(" cloud , , mlx ")

    assert list(backends) == ["cloud", "mlx"]


def test_load_backends_rejects_unknown_id() -> None:
    with pytest.raises(BackendResolutionError, match="unknown LLM backend id"):
        load_backends("ghost")


def test_mlx_base_url_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLX_PLATFORM_BASE_URL", "http://127.0.0.1:5900/v1")

    backends = load_backends("mlx")

    assert backends["mlx"].base_url == "http://127.0.0.1:5900/v1"
