"""Public API for ``pkg_llm_backend``.

Everything app/tests import lives here. Internal modules are private —
imports must target ``pkg_llm_backend.api`` only (AGENTS.md).
"""

from __future__ import annotations

__all__ = [
    "DEFAULT_LLM_BACKENDS",
    "Backend",
    "BackendResolutionError",
    "LLMBackendConfig",
    "ensure_model_available",
    "generate_text",
    "load_backends",
]

from .backend import Backend
from .config import DEFAULT_LLM_BACKENDS, BackendResolutionError, LLMBackendConfig, load_backends
from .llm import ensure_model_available, generate_text
