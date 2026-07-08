"""Worker and language routes.

``GET /api/workers`` and ``GET /api/languages?worker=``. Mounted under
``/api`` by the app factory.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from .workers import (
    WorkerResolutionError,
    fetch_languages,
    probe_workers,
    worker_base_url,
    workers_env,
)

router = APIRouter(tags=["workers"])


@router.get("/workers")
async def list_workers() -> dict[str, object]:
    infos = workers_env()
    statuses = await probe_workers(infos)
    return {
        "workers": [
            {"id": s.id, "label": s.label, "healthy": s.healthy} for s in statuses
        ]
    }


@router.get("/languages")
async def list_languages(
    worker: str = Query(..., description="Worker id to query"),
) -> dict[str, object]:
    try:
        base_url = worker_base_url(worker)
    except WorkerResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    try:
        return await fetch_languages(base_url)
    except Exception as exc:  # noqa: BLE001 — surface worker failure as 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"worker languages call failed: {exc}",
        ) from exc
