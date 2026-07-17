from types import SimpleNamespace

import pytest
from pkg_llm_backend import llm
from pkg_llm_backend.config import LLMBackendConfig


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake_client: object) -> None:
    def _client(_config: LLMBackendConfig, _api_key: str) -> object:
        return fake_client

    monkeypatch.setattr(llm, "_client", _client)


def _mlx_config() -> LLMBackendConfig:
    return LLMBackendConfig(
        model="local-chat",
        base_url="http://127.0.0.1:5900/v1",
        project="srt-flow",
        api_key="local",
        verify_model_alias=True,
    )


def _cloud_config() -> LLMBackendConfig:
    return LLMBackendConfig(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
        api_key_env="SRT_TEST_DEEPSEEK_KEY",
        extra_body={"thinking": {"type": "disabled"}},
        verify_model_alias=False,
    )


def test_generate_text_sends_only_documented_fields_for_mlx(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _mlx_config()
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> object:
        captured.update(kwargs)
        message = SimpleNamespace(content='[{"id": 1, "zh": "你好"}]')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    _patch_client(monkeypatch, fake_client)

    result = llm.generate_text("prompt", config)

    assert result == '[{"id": 1, "zh": "你好"}]'
    assert captured["model"] == config.model
    assert captured.get("extra_body") is None


def test_generate_text_sends_extra_body_for_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _cloud_config()
    monkeypatch.setenv(config.api_key_env or "", "test-key")
    captured: dict[str, object] = {}

    def fake_create(**kwargs: object) -> object:
        captured.update(kwargs)
        message = SimpleNamespace(content='[{"id": 1, "zh": "你好"}]')
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    _patch_client(monkeypatch, fake_client)

    llm.generate_text("prompt", config)

    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}


def test_generate_text_rejects_empty_content(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _mlx_config()

    def fake_create(**_kwargs: object) -> object:
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" "))])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
    )
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(RuntimeError, match="empty content"):
        llm.generate_text("prompt", config)


def test_ensure_model_available_skips_check_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _cloud_config()
    monkeypatch.setenv(config.api_key_env or "", "test-key")

    def exploding(_config: object, _key: object) -> object:
        raise AssertionError("should not build a client when verify_model_alias is False")

    monkeypatch.setattr(llm, "_client", exploding)

    llm.ensure_model_available(config)  # does not raise


def test_ensure_model_available_raises_for_unknown_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _mlx_config()

    def fake_list() -> object:
        return SimpleNamespace(data=[SimpleNamespace(id="some-other-alias")])

    fake_client = SimpleNamespace(models=SimpleNamespace(list=fake_list))
    _patch_client(monkeypatch, fake_client)

    with pytest.raises(RuntimeError, match="no model alias"):
        llm.ensure_model_available(config)


def test_ensure_model_available_passes_for_known_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _mlx_config()

    def fake_list() -> object:
        return SimpleNamespace(data=[SimpleNamespace(id=config.model)])

    fake_client = SimpleNamespace(models=SimpleNamespace(list=fake_list))
    _patch_client(monkeypatch, fake_client)

    llm.ensure_model_available(config)  # does not raise


def test_missing_api_key_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _cloud_config()
    monkeypatch.delenv(config.api_key_env or "", raising=False)

    with pytest.raises(RuntimeError, match="Missing API key environment variable"):
        llm.ensure_model_available(config)
