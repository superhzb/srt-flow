"""HTTP routes for jobs.

Mounted under ``/api`` by the app: ``POST /jobs``, ``GET /jobs``,
``GET /jobs/{id}``, ``GET /jobs/{id}/download``. Slice-3 still runs in
``AUTH_MODE=dev`` — the dev user owns every job, so the routes trust
``app.state.job_ctx.dev_user_id`` directly. Slice 4 swaps in a real
``get_current_user`` dependency.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pkg_srt_services.api import Cue, build_stacked_srt, dict_to_cue, parse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlmodel import col, select

from .credits import balance_snapshot, billed_minutes, source_minutes
from .db import session_scope
from .events import record_event
from .models import Job, User, dropped_from_json, progress_from_json, tgt_langs_from_csv
from .orchestration import EnqueueError, clean_target_langs, enqueue
from .workers import WorkerResolutionError

__all__ = ["router"]

router = APIRouter(prefix="/jobs", tags=["jobs"])


async def require_job_user() -> User:
    """Composition seam overridden by the host app's auth dependency."""
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cues: list[dict[str, Any]] = Field(min_length=1)
    source_lang: str | None = None
    source_line: int | None = Field(default=None, ge=0, le=1)
    targets: list[str] = Field(min_length=1)
    worker: str = Field(min_length=1)
    filename: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_source_mode(self) -> CreateJobRequest:
        if self.source_line is None and (self.source_lang is None or not self.source_lang.strip()):
            raise ValueError("source_lang is required when source_line is not set")
        return self

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("filename must not contain control characters")
        if "/" in value or "\\" in value or ".." in value:
            raise ValueError("filename must be a display name, not a path")
        return value


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    request: Request,
    body: CreateJobRequest,
    user: Annotated[User, Depends(require_job_user)],
) -> dict[str, str]:
    """Persist a new pending job and enqueue it for the worker_loop."""
    ctx = request.app.state.job_ctx
    cues = _dict_to_cues(body.cues)
    source_lang = body.source_lang.strip() if body.source_lang else ""
    carried_lang: str | None = None
    if body.source_line is not None:
        if ctx.bilingual_detector is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="file is not bilingual",
            )
        detection = ctx.bilingual_detector(cues)
        if not detection.is_bilingual or len(detection.line_langs) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="file is not bilingual",
            )
        source_lang = detection.line_langs[body.source_line]
        carried_lang = detection.line_langs[1 - body.source_line]

    clean_targets = clean_target_langs(body.targets, source_lang)
    if carried_lang in clean_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="carried language cannot also be a translation target",
        )
    minutes = source_minutes(cues)
    # Option A pricing: bill source minutes once per target language. Use the
    # deduped target list so the pre-check matches what enqueue persists.
    lang_count = len(clean_targets)
    billed = billed_minutes(minutes, lang_count)
    try:
        with session_scope() as session:
            free_limit = int(getattr(request.app.state, "free_tier_monthly_limit", 30))
            balance = balance_snapshot(session, user.id, free_limit)
            if balance.purchased_minutes < 0 or billed > balance.available_minutes:
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "message": "Insufficient subtitle minutes",
                        "required_minutes": billed,
                        "available_minutes": balance.available_minutes,
                    },
                )
            result = enqueue(
                ctx,
                session,
                cues=cues,
                source_lang=source_lang,
                targets=clean_targets,
                worker_id=body.worker,
                filename=body.filename,
                user_id=user.id,
                source_minutes=minutes,
                carried_lang=carried_lang,
                source_line=body.source_line,
            )
            record_event(
                session,
                "job_created",
                user_id=user.id,
                dedup_key=result.job_id,
                props={
                    "job_id": result.job_id,
                    "src_lang": source_lang,
                    "tgt_langs": clean_targets,
                },
            )
            ctx.queue.put_nowait(result.job_id)
    except EnqueueError as exc:
        # Unknown worker (typed cause) → 404; bad cues/targets → 400.
        if isinstance(exc.__cause__, WorkerResolutionError):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"job_id": result.job_id}


@router.get("")
async def list_jobs(
    request: Request, user: Annotated[User, Depends(require_job_user)]
) -> dict[str, Any]:
    """List the dev user's jobs, newest first."""
    with session_scope() as session:
        stmt = select(Job).where(Job.user_id == user.id).order_by(col(Job.created_at).desc())
        jobs = session.exec(stmt).all()
        # Build the response inside the session — Job attrs are only
        # guaranteed live while the session is open.
        summary = [j.model_dump_summary() for j in jobs]
    return {"jobs": summary}


@router.get("/{job_id}")
async def get_job(
    request: Request,
    job_id: str,
    user: Annotated[User, Depends(require_job_user)],
) -> dict[str, Any]:
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None or job.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        out: dict[str, Any] = {
            "id": job.id,
            "filename": job.filename,
            "status": job.status,
            "progress": job.progress,
            "worker": job.worker,
            "src_lang": job.src_lang,
            "tgt_langs": tgt_langs_from_csv(job.tgt_langs),
            "carried_langs": tgt_langs_from_csv(job.carried_langs),
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error_kind": job.error_kind,
            "attempts": job.attempts,
            "source_minutes": job.source_minutes,
        }
        progress = progress_from_json(job.progress_by_target)
        targets = tgt_langs_from_csv(job.tgt_langs)
        out["targets"] = [_target_progress(lang, progress, job.status) for lang in targets]
        out["eta_seconds"] = _eta_seconds(job, progress)
        if job.error is not None:
            out["error"] = job.error
        if job.error_detail is not None:
            out["error_detail"] = job.error_detail
        if job.failed_target is not None:
            out["failed_target"] = job.failed_target
        if job.dropped_by_target is not None:
            out["dropped_by_target"] = dropped_from_json(job.dropped_by_target)
        if job.status == "done":
            targets = tgt_langs_from_csv(job.tgt_langs)
            carried = tgt_langs_from_csv(job.carried_langs)
            out["results"] = [
                {
                    "lang": lang,
                    "download_url": f"/api/jobs/{job.id}/download?lang={lang}",
                }
                for lang in [*carried, *targets]
            ]
            default_order = [job.src_lang, *carried, *targets]
            query = urlencode({"langs": ",".join(default_order)})
            out["stacked"] = {
                "default_order": default_order,
                "download_url": f"/api/jobs/{job.id}/download?{query}",
            }
        return out


@router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    request: Request,
    job_id: str,
    user: Annotated[User, Depends(require_job_user)],
) -> dict[str, str]:
    """Re-queue a failed job without re-uploading — ``input.srt`` is retained.

    Resets the row to ``pending`` and clears the failure fields, then puts the
    id back on the worker queue. ``attempts`` increments naturally on the next
    claim. Unlimited retries; billing still happens only on eventual success.
    """
    ctx = request.app.state.job_ctx
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None or job.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        if job.status != "failed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"job is {job.status}, not failed",
            )
        job.status = "pending"
        job.error = None
        job.error_kind = None
        job.error_detail = None
        job.failed_target = None
        job.finished_at = None
        job.progress = 0.0
        job.progress_by_target = None
        session.add(job)
        record_event(
            session,
            "job_retried",
            user_id=job.user_id,
            # attempts is the count of prior claims — unique per retry.
            dedup_key=f"{job_id}:retried:{job.attempts}",
            props={"job_id": job_id, "attempt": job.attempts},
        )
        session.commit()
    ctx.queue.put_nowait(job_id)
    return {"job_id": job_id}


def _target_progress(
    lang: str, progress: dict[str, dict[str, int]], job_status: str
) -> dict[str, Any]:
    item = progress.get(lang)
    if job_status == "done":
        return {"lang": lang, "status": "done", "progress": 1.0}
    if item is None:
        return {"lang": lang, "status": "queued", "progress": 0.0}
    total = item["total"]
    fraction = min(1.0, item["done"] / total) if total > 0 else 0.0
    return {"lang": lang, "status": "done" if fraction >= 1 else "running", "progress": fraction}


def _eta_seconds(job: Job, progress: dict[str, dict[str, int]]) -> float | None:
    if job.status == "done":
        return 0.0
    if job.started_at is None:
        return None
    from datetime import UTC, datetime

    started = job.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - started).total_seconds()
    done = sum(item["done"] for item in progress.values())
    total = sum(item["total"] for item in progress.values())
    if elapsed <= 0 or done <= 0:
        return None
    return max(0.0, (total - done) / (done / elapsed))


@router.get("/{job_id}/download")
async def download_job(
    request: Request,
    job_id: str,
    user: Annotated[User, Depends(require_job_user)],
    lang: Annotated[str | None, Query(description="Target language to download")] = None,
    langs: Annotated[str | None, Query(description="Ordered languages to stack")] = None,
) -> StreamingResponse:
    ctx = request.app.state.job_ctx
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None or job.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
        if job.status != "done":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"job is {job.status}, not done",
            )
        targets = tgt_langs_from_csv(job.tgt_langs)
        carried = tgt_langs_from_csv(job.carried_langs)
        source_lang = job.src_lang
        if langs is None and lang is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="lang or langs required",
            )
        downloadable = {*targets, *carried}
        if langs is None and lang not in downloadable:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"job has no output for language {lang!r}",
            )

    if langs is not None:
        order = list(dict.fromkeys(part.strip() for part in langs.split(",") if part.strip()))
        if not order:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="at least one language required",
            )
        valid = {source_lang, *targets, *carried}
        for requested_lang in order:
            if requested_lang not in valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"unknown language {requested_lang} for this job",
                )
        try:
            source_data = ctx.storage.get(user.id, job_id, "input.srt")
            source_cues = parse(source_data.decode("utf-8"))
            target_texts: dict[str, dict[int, str]] = {}
            for requested_lang in order:
                if requested_lang == source_lang:
                    continue
                target_data = ctx.storage.get(user.id, job_id, f"output.{requested_lang}.srt")
                target_texts[requested_lang] = {
                    cue.index: cue.text for cue in parse(target_data.decode("utf-8"))
                }
        except Exception as exc:  # noqa: BLE001 — storage/parse miss is unavailable output
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"output file missing: {exc}",
            ) from exc
        data = build_stacked_srt(source_lang, source_cues, target_texts, order).encode()
        filename = f"{job_id}.stacked.srt"
    else:
        try:
            data = ctx.storage.get(user.id, job_id, f"output.{lang}.srt")
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
