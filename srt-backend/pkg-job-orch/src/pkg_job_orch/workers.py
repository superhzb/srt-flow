"""Worker registry — in-process LLM backend rows.

Slice 2/3 had this proxy HTTP to standalone worker services (``WORKERS=id=url,...``).
Phase B collapsed the workers into this process: a "worker" is now just an id
that resolves to an in-process ``pkg_llm_backend.LLMBackendConfig`` row. The
HTTP routes ``/api/workers`` and ``/api/languages`` keep their exact shape —
only what backs them changed, from "proxy to a worker" to "look up a
registry row".

``LLM_BACKENDS=id,id,...`` (env, parsed by ``pkg_llm_backend.load_backends``)
decides which ids are available; local dev/test enables both ``mlx`` and
``cloud``, cloud deploy enables only ``cloud``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from pkg_llm_backend.api import Backend, BackendResolutionError, LLMBackendConfig, load_backends
from pkg_translator.api import TranslationConfig, available_languages

__all__ = [
    "WorkerInfo",
    "WorkerResolutionError",
    "WorkerStatus",
    "fetch_languages",
    "probe_workers",
    "worker_backend_config",
    "worker_base_url",
    "workers_env",
]

_HEALTH_TIMEOUT: float = 1.0

# Pretty labels for the well-known ids; unknown ids fall back to title-case.
_LABELS: dict[str, str] = {
    "cloud": "Cloud (DeepSeek)",
    "mlx": "Local MLX",
}

_BACKEND = Backend()


@dataclass(frozen=True)
class WorkerInfo:
    id: str
    base_url: str

    @property
    def label(self) -> str:
        return _LABELS.get(self.id, self.id.title())


@dataclass(frozen=True)
class WorkerStatus:
    id: str
    label: str
    healthy: bool


class WorkerResolutionError(ValueError):
    """Raised when a worker id cannot be resolved to a backend config."""


def workers_env() -> list[WorkerInfo]:
    """List the enabled worker ids (registry rows), in ``LLM_BACKENDS`` order."""
    try:
        backends = load_backends()
    except BackendResolutionError as exc:
        raise WorkerResolutionError(str(exc)) from exc
    return [
        WorkerInfo(id=worker_id, base_url=config.base_url) for worker_id, config in backends.items()
    ]


def worker_backend_config(worker_id: str) -> LLMBackendConfig:
    """Resolve ``worker_id`` -> its ``LLMBackendConfig`` or raise ``WorkerResolutionError``."""
    try:
        backends = load_backends()
    except BackendResolutionError as exc:
        raise WorkerResolutionError(str(exc)) from exc
    config = backends.get(worker_id)
    if config is None:
        raise WorkerResolutionError(f"unknown worker id: {worker_id!r}")
    return config


def worker_base_url(worker_id: str) -> str:
    """Resolve ``worker_id`` -> its backend ``base_url`` or raise ``WorkerResolutionError``."""
    return worker_backend_config(worker_id).base_url


async def probe_workers(infos: list[WorkerInfo]) -> list[WorkerStatus]:
    """Probe each worker's backend reachability in parallel with a tight timeout.

    Unreachable / timed-out backends are reported ``healthy=False`` — never
    raised. The list order matches ``infos``.
    """

    async def _one(info: WorkerInfo) -> WorkerStatus:
        try:
            config = worker_backend_config(info.id)
            await asyncio.wait_for(
                asyncio.to_thread(_BACKEND.ensure_model_available, config),
                timeout=_HEALTH_TIMEOUT,
            )
            ok = True
        except Exception:  # noqa: BLE001 — any failure means "unhealthy", never raise
            ok = False
        return WorkerStatus(id=info.id, label=info.label, healthy=ok)

    return await asyncio.gather(*(_one(i) for i in infos))


async def fetch_languages(worker_id: str) -> dict[str, object]:
    """Resolve ``worker_id`` (validating it exists) and return the shared language catalog.

    All backends share one ``pkg_translator`` language catalog; ``worker_id``
    is only validated here to preserve the pre-merge 404-on-unknown-worker
    contract of ``GET /api/languages?worker=...``.
    """
    worker_backend_config(worker_id)
    languages_path = TranslationConfig().languages_path
    return {"languages": available_languages(languages_path)}
