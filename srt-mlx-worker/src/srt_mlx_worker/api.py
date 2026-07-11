"""Public API for the SRT MLX worker.

The FastAPI factory (``create_app``) and the MLX-backend adapter live here
rather than in a separate ``app.py``: ``create_app`` is the worker's public
entry point consumed by tests, and ``server.py`` is the uvicorn launcher that
imports it. Keeping the factory out of ``server.py`` avoids an import side
effect — ``server.py`` eagerly builds the module-level ``app`` for uvicorn, so
importing it from here would construct the app at import time.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, cast

from fastapi import FastAPI
from pkg_translator.api import (
    BatchProgress,
    LangConfig,
    LLMBackend,
    PairConfig,
    ProgressCallback,
    TranslationRequest,
    TranslationResponse,
    Translator,
    available_languages,
    load_lang,
    load_template,
    make_pair,
    translate_segments,
)
from pkg_translator.api import (
    TranslationConfig as BaseTranslationConfig,
)
from pkg_translator.api import (
    create_app as _create_app,
)

from . import llm
from .config import TranslationConfig

__all__ = [
    "BatchProgress",
    "LLMBackend",
    "LangConfig",
    "PairConfig",
    "ProgressCallback",
    "TranslationConfig",
    "TranslationRequest",
    "TranslationResponse",
    "Translator",
    "available_languages",
    "create_app",
    "load_lang",
    "load_template",
    "make_pair",
    "translate_segments",
]


class _MlxBackend:
    """Binds the local MLX LLM impl to the core LLMBackend protocol."""

    def ensure_model_available(self, config: BaseTranslationConfig) -> None:
        llm.ensure_model_available(cast(TranslationConfig, config))

    def generate_text(self, prompt: str, config: BaseTranslationConfig) -> str:
        return llm.generate_text(prompt, cast(TranslationConfig, config))


def create_app(
    default_config: TranslationConfig | None = None,
    *,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[Any]] | None = None,
) -> FastAPI:
    """Build the MLX-worker FastAPI app with the local MLX backend wired in."""
    return _create_app(
        default_config or TranslationConfig(),
        backend=_MlxBackend(),
        title="SRT MLX Worker",
        lifespan=lifespan,
    )
