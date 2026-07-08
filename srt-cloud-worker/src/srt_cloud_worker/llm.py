"""Cloud-backed text generation."""

import logging
import os

from openai import OpenAI

from .config import TranslationConfig

logger = logging.getLogger(__name__)


def ensure_model_available(config: TranslationConfig) -> None:
    _api_key(config)


def generate_text(prompt: str, config: TranslationConfig) -> str:
    key = _api_key(config)
    client = OpenAI(
        api_key=key,
        base_url=config.base_url,
        timeout=config.request_timeout,
    )
    logger.debug("Sending %d chars to DeepSeek model %s", len(prompt), config.model)

    try:
        response = client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
    except Exception as exc:
        raise RuntimeError(f"Cloud generation failed: {exc}") from exc

    content = response.choices[0].message.content
    if content is None or not content.strip():
        raise RuntimeError("Cloud generation returned empty content")
    return content


def _api_key(config: TranslationConfig) -> str:
    key = os.environ.get(config.api_key_env)
    if key is None or not key.strip():
        raise RuntimeError(f"Missing API key environment variable: {config.api_key_env}")
    return key
