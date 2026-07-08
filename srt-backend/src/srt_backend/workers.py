"""Worker registry and HTTP client.

Workers expose ``/health``, ``/languages``, ``/translate``, and
``/translate/stream``. This module owns:

- Parsing ``WORKERS`` env (``id=url,id=url,…``) into immutable ``WorkerInfo``.
- Resolving a worker id to its base URL (raises if unknown).
- Probing ``/health`` concurrently to mark each worker ``healthy``.
- Proxying ``/languages`` verbatim.

The streaming ``POST /translate/stream`` call lives in ``translation.py`` so
its lifecycle (open client + read lines + close) is contained in one place.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import httpx2

__all__ = [
    "DEFAULT_WORKERS",
    "WorkerInfo",
    "WorkerResolutionError",
    "WorkerStatus",
    "workers_env",
    "worker_base_url",
    "probe_workers",
    "fetch_languages",
]

# Default dev topology (matches the Makefile port layout).
DEFAULT_WORKERS: str = "cloud=http://localhost:5733,mlx=http://localhost:5732"

_HEALTH_TIMEOUT: float = 1.0
_PROXY_TIMEOUT: float = 5.0

# Pretty labels for the well-known dev ids; unknown ids fall back to title-case.
_LABELS: dict[str, str] = {
    "cloud": "Cloud (DeepSeek)",
    "mlx": "Local MLX",
}


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
    """Raised when a worker id cannot be resolved to a base URL."""


def workers_env(raw: str | None = None) -> list[WorkerInfo]:
    """Parse the ``WORKERS`` env string.

    Format: ``id1=url1,id2=url2``. Whitespace around tokens is stripped.
    Empty entries are skipped. Order is preserved (deterministic UI list).
    """
    text = raw if raw is not None else os.environ.get("WORKERS", DEFAULT_WORKERS)
    out: list[WorkerInfo] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise WorkerResolutionError(
                f"invalid WORKERS entry {token!r}: expected 'id=url'"
            )
        wid, url = token.split("=", 1)
        wid = wid.strip()
        url = url.strip()
        if not wid or not url:
            raise WorkerResolutionError(
                f"invalid WORKERS entry {token!r}: empty id or url"
            )
        out.append(WorkerInfo(id=wid, base_url=url.rstrip("/")))
    return out


def worker_base_url(worker_id: str, raw: str | None = None) -> str:
    """Resolve ``worker_id`` → base URL or raise ``WorkerResolutionError``."""
    for info in workers_env(raw):
        if info.id == worker_id:
            return info.base_url
    raise WorkerResolutionError(f"unknown worker id: {worker_id!r}")


async def probe_workers(infos: list[WorkerInfo]) -> list[WorkerStatus]:
    """Probe each worker's ``/health`` in parallel with a tight timeout.

    Unreachable / timed-out workers are reported ``healthy=False`` — never
    raised. The list order matches ``infos``.
    """

    async def _one(info: WorkerInfo) -> WorkerStatus:
        try:
            async with httpx2.AsyncClient(timeout=_HEALTH_TIMEOUT) as client:
                resp = await client.get(f"{info.base_url}/health")
                ok = resp.status_code == 200
        except (httpx2.HTTPError, OSError):
            ok = False
        return WorkerStatus(id=info.id, label=info.label, healthy=ok)

    return await asyncio.gather(*(_one(i) for i in infos))


async def fetch_languages(base_url: str) -> dict[str, object]:
    """Proxy ``GET {base_url}/languages`` and return its JSON verbatim."""
    async with httpx2.AsyncClient(timeout=_PROXY_TIMEOUT) as client:
        resp = await client.get(f"{base_url}/languages")
        resp.raise_for_status()
        return resp.json()
