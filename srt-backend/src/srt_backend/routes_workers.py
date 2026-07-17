"""Worker + language routes.

Thin HTTP layer over ``pkg_job_orch``'s in-process LLM backend registry.
Job-orch owns the worker surface (registry, health check, language
catalog); these routes just expose it under ``/api``.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from pkg_job_orch.api import (
    WorkerResolutionError,
    fetch_languages,
    probe_workers,
    workers_env,
)

router = APIRouter(tags=["workers"])


@router.get("/workers")
async def list_workers() -> dict[str, object]:
    infos = workers_env()
    statuses = await probe_workers(infos)
    return {"workers": [{"id": s.id, "label": s.label, "healthy": s.healthy} for s in statuses]}


@router.get("/languages")
async def list_languages(
    worker: str = Query(..., description="Worker id to query"),
) -> dict[str, object]:
    try:
        return await fetch_languages(worker)
    except WorkerResolutionError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surface backend failure as 502
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"worker languages call failed: {exc}",
        ) from exc
