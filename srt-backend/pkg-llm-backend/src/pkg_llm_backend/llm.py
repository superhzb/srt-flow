"""Text generation via an OpenAI-compatible endpoint (cloud or local mlx-platform).

One implementation for both backends — behavior differences are config-driven
(see ``config.py``): ``extra_body`` is DeepSeek-only, ``project`` sends
``X-MLX-Project`` for mlx-platform attribution, and ``verify_model_alias``
toggles the ``GET /v1/models`` reachability check (mlx-platform rejects an
unknown alias with a clear error; DeepSeek has no equivalent alias registry).
"""

from __future__ import annotations

import logging
import os

from openai import OpenAI

from .config import LLMBackendConfig

logger = logging.getLogger(__name__)


def ensure_model_available(config: LLMBackendConfig) -> None:
    key = _resolve_api_key(config)
    if not config.verify_model_alias:
        return
    client = _client(config, key)
    ids = {m.id for m in client.models.list().data}
    if config.model not in ids:
        raise RuntimeError(f"backend has no model alias {config.model!r}; available: {sorted(ids)}")


def generate_text(prompt: str, config: LLMBackendConfig) -> str:
    key = _resolve_api_key(config)
    client = _client(config, key)
    logger.debug("Sending %d chars to backend model %s", len(prompt), config.model)

    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            stream=False,
            extra_body=config.extra_body,
        )
    except Exception as exc:
        raise RuntimeError(f"backend generation failed: {exc}") from exc

    content = response.choices[0].message.content
    if content is None or not content.strip():
        raise RuntimeError("backend returned empty content")
    return content


def _resolve_api_key(config: LLMBackendConfig) -> str:
    if config.api_key is not None:
        return config.api_key
    if config.api_key_env is not None:
        key = os.environ.get(config.api_key_env)
        if key is None or not key.strip():
            raise RuntimeError(f"Missing API key environment variable: {config.api_key_env}")
        return key
    raise RuntimeError("backend config has neither api_key nor api_key_env")


def _client(config: LLMBackendConfig, api_key: str) -> OpenAI:
    headers = {"X-MLX-Project": config.project} if config.project is not None else None
    return OpenAI(
        api_key=api_key,
        base_url=config.base_url,
        timeout=config.request_timeout,
        default_headers=headers,
    )
