"""HTTP routes for jobs.

Mounted under ``/api`` by the app: ``POST /jobs``, ``GET /jobs``,
``GET /jobs/{id}``, ``GET /jobs/{id}/download``. Slice-3 still runs in
``AUTH_MODE=dev`` — the dev user owns every job, so the routes trust
``app.state.job_ctx.dev_user_id`` directly. Slice 4 swaps in a real
``get_current_user`` dependency.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pkg_srt_services.api import Cue, dict_to_cue
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import col, select

from .db import session_scope
from .models import Job, dropped_from_json, tgt_langs_from_csv
from .orchestration import EnqueueError, enqueue
from .workers import WorkerResolutionError

__all__ = ["router"]

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cues: list[dict[str, Any]] = Field(min_length=1)
    source_lang: str = Field(min_length=1)
    targets: list[str] = Field(min_length=1)
    worker: str = Field(min_length=1)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_job(request: Request, body: CreateJobRequest) -> dict[str, str]:
    """Persist a new pending job and enqueue it for the worker_loop."""
    ctx = request.app.state.job_ctx
    cues = _dict_to_cues(body.cues)
    try:
        with session_scope() as session:
            result = enqueue(
                ctx,
                session,
                cues=cues,
                source_lang=body.source_lang,
                targets=body.targets,
                worker_id=body.worker,
            )
            ctx.queue.put_nowait(result.job_id)
    except EnqueueError as exc:
        # Unknown worker (typed cause) → 404; bad cues/targets → 400.
        if isinstance(exc.__cause__, WorkerResolutionError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"job_id": result.job_id}


@router.get("")
async def list_jobs(request: Request) -> dict[str, Any]:
    """List the dev user's jobs, newest first."""
    ctx = request.app.state.job_ctx
    with session_scope() as session:
        stmt = (
            select(Job).where(Job.user_id == ctx.dev_user_id).order_by(col(Job.created_at).desc())
        )
        jobs = session.exec(stmt).all()
        # Build the response inside the session — Job attrs are only
        # guaranteed live while the session is open.
        summary = [j.model_dump_summary() for j in jobs]
    return {"jobs": summary}


@router.get("/{job_id}")
async def get_job(request: Request, job_id: str) -> dict[str, Any]:
    ctx = request.app.state.job_ctx
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None or job.user_id != ctx.dev_user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        out: dict[str, Any] = {
            "id": job.id,
            "status": job.status,
            "progress": job.progress,
            "worker": job.worker,
            "src_lang": job.src_lang,
            "tgt_langs": tgt_langs_from_csv(job.tgt_langs),
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error_kind": job.error_kind,
            "attempts": job.attempts,
        }
        if job.error is not None:
            out["error"] = job.error
        if job.dropped_by_target is not None:
            out["dropped_by_target"] = dropped_from_json(job.dropped_by_target)
        if job.status == "done":
            out["results"] = [
                {
                    "lang": lang,
                    "download_url": f"/api/jobs/{job.id}/download?lang={lang}",
                }
                for lang in tgt_langs_from_csv(job.tgt_langs)
            ]
        return out


@router.get("/{job_id}/download")
async def download_job(
    request: Request,
    job_id: str,
    lang: Annotated[str, Query(description="Target language to download")],
) -> StreamingResponse:
    ctx = request.app.state.job_ctx
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None or job.user_id != ctx.dev_user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        if job.status != "done":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"job is {job.status}, not done",
            )
        targets = tgt_langs_from_csv(job.tgt_langs)
        if lang not in targets:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"job has no output for language {lang!r}",
            )

    try:
        data = ctx.storage.get(ctx.dev_user_id, job_id, f"output.{lang}.srt")
    except Exception as exc:  # noqa: BLE001 — surface storage failure as 404/500
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"output file missing: {exc}",
        ) from exc

    filename = f"{job_id}.{lang}.srt"
    return StreamingResponse(
        iter([data]),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _dict_to_cues(items: list[dict[str, Any]]) -> list[Cue]:
    out: list[Cue] = []
    for d in items:
        try:
            out.append(dict_to_cue(d))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid cue: {exc}",
            ) from exc
    return out
