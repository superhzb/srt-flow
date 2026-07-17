"""Binds the OpenAI-client LLM impl to the ``pkg_translator`` LLMBackend protocol."""

from __future__ import annotations

from typing import cast

from pkg_translator.api import TranslationConfig as BaseTranslationConfig

from . import llm
from .config import LLMBackendConfig


class Backend:
    """The one ``LLMBackend`` implementation, parameterized entirely by config."""

    def ensure_model_available(self, config: BaseTranslationConfig) -> None:
        llm.ensure_model_available(cast(LLMBackendConfig, config))

    def generate_text(self, prompt: str, config: BaseTranslationConfig) -> str:
        return llm.generate_text(prompt, cast(LLMBackendConfig, config))
