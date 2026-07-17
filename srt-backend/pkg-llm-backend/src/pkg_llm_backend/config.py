"""Runtime configuration for the in-process LLM backend registry.

Each registry row is a config-driven ``LLMBackendConfig`` — the union of what
used to be ``srt-cloud-worker/config.py`` (DeepSeek) and
``srt-mlx-worker/config.py`` (mlx-platform gateway). The two are NOT
symmetric: cloud reads its key from an env var at call time (``api_key_env``)
and has no ``project``/reachability check; mlx uses a literal loopback
placeholder key, sends ``X-MLX-Project``, and verifies its model alias via
``GET /v1/models`` before first use. Both differences are captured as config
fields (``api_key`` vs ``api_key_env``, ``project``, ``verify_model_alias``,
``extra_body``) so ``llm.py`` has exactly one implementation.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from pkg_translator.api import TranslationConfig as BaseTranslationConfig

__all__ = [
    "DEFAULT_LLM_BACKENDS",
    "BackendResolutionError",
    "LLMBackendConfig",
    "load_backends",
]

# Local dev/test enables both rows; cloud deploy overrides this to "cloud"
# only (the mlx path never runs in the cloud — see MLX_PLATFORM_MIGRATION.md).
DEFAULT_LLM_BACKENDS = "mlx,cloud"


@dataclass(frozen=True)
class LLMBackendConfig(BaseTranslationConfig):
    model: str = ""
    base_url: str = ""
    api_key: str | None = None
    api_key_env: str | None = None
    project: str | None = None
    extra_body: dict[str, object] | None = None
    verify_model_alias: bool = False
    request_timeout: float = 60.0


class BackendResolutionError(ValueError):
    """Raised when an ``LLM_BACKENDS`` entry cannot be resolved to a config."""


def _mlx_config() -> LLMBackendConfig:
    # Confirm the gateway port with the mlx-platform team before cutover;
    # 5900 is a placeholder. Aliases, never model paths — the gateway
    # rejects arbitrary paths.
    return LLMBackendConfig(
        model=os.environ.get("MLX_PLATFORM_MODEL", "local-chat"),
        base_url=os.environ.get("MLX_PLATFORM_BASE_URL", "http://127.0.0.1:5900/v1"),
        project="srt-flow",
        api_key="local",
        verify_model_alias=True,
        batch_size=10,
        max_tokens=2048,
        request_timeout=120.0,
    )


def _cloud_config() -> LLMBackendConfig:
    return LLMBackendConfig(
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        api_key_env="DEEPSEEK_API_KEY",
        extra_body={"thinking": {"type": "disabled"}},
        verify_model_alias=False,
        batch_size=100,
        max_tokens=8192,
        request_timeout=60.0,
    )


_BUILDERS: dict[str, Callable[[], LLMBackendConfig]] = {
    "mlx": _mlx_config,
    "cloud": _cloud_config,
}


def load_backends(raw: str | None = None) -> dict[str, LLMBackendConfig]:
    """Parse ``LLM_BACKENDS`` (``id1,id2,...``) into an ordered id -> config map.

    A fresh read on every call (no caching) — same ergonomics as
    ``pkg_job_orch.config.load_settings`` — so tests can
    ``monkeypatch.setenv("LLM_BACKENDS", ...)`` and observe the change
    immediately. Unknown ids raise ``BackendResolutionError``.
    """
    text = raw if raw is not None else os.environ.get("LLM_BACKENDS", DEFAULT_LLM_BACKENDS)
    backends: dict[str, LLMBackendConfig] = {}
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        builder = _BUILDERS.get(token)
        if builder is None:
            raise BackendResolutionError(f"unknown LLM backend id: {token!r}")
        backends[token] = builder()
    return backends
