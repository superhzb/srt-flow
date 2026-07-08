"""Translation job routes.

``POST /api/translate`` enqueues a background task that streams worker
``/translate/stream``; ``GET /api/translate/{job_id}`` polls status.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status
from pkg_srt_services.api import Cue, ParseError
from pydantic import BaseModel, ConfigDict, Field

from .jobs import JobStore
from .translation import run_translation
from .workers import WorkerResolutionError, worker_base_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["translate"])

# Process-local store for slice 2. ``pkg-job-orch`` + SQLite replaces this
# in slice 3.
_store = JobStore()


class TranslateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cues: list[dict[str, object]] = Field(min_length=1)
    source_lang: str = Field(min_length=1)
    targets: list[str] = Field(min_length=1)
    worker: str = Field(min_length=1)


@router.post("/translate", status_code=status.HTTP_202_ACCEPTED)
async def start_translate(request: TranslateRequest) -> dict[str, str]:
    """Spawn a streaming translation job; return its id immediately."""
    try:
        base_url = worker_base_url(request.worker)
    except WorkerResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    # Validate cues up front: backend trusts the slice-1 parser shape, but
    # a malformed body should 400 rather than fail mid-stream.
    try:
        cues = [_dict_to_cue(c) for c in request.cues]
    except (KeyError, ValueError, ParseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid cue: {exc}",
        ) from exc

    # Dedup targets, drop the source if it slipped in, preserve order.
    seen: set[str] = set()
    targets: list[str] = []
    for t in request.targets:
        if t == request.source_lang or t in seen or not t:
            continue
        seen.add(t)
        targets.append(t)
    if not targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="at least one target language is required",
        )

    job = _store.create()
    asyncio.create_task(
        run_translation(
            job=job,
            cues=cues,
            source_lang=request.source_lang,
            targets=targets,
            worker_base_url=base_url,
        )
    )
    return {"job_id": job.job_id}


@router.get("/translate/{job_id}")
async def get_translate(job_id: str) -> dict[str, object]:
    job = _store.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
        )
    out: dict[str, object] = {
        "status": job.status,
        "progress": job.progress,
    }
    if job.results is not None:
        out["results"] = job.results
    if job.error is not None:
        out["error"] = job.error
    return out


def _dict_to_cue(d: dict[str, object]) -> Cue:
    """Rebuild a ``Cue`` from the wire dict (sent back by /prepare)."""
    try:
        return Cue(
            index=int(d["index"]),  # type: ignore[arg-type]
            start=str(d["start"]),
            end=str(d["end"]),
            text=str(d["text"]),
        )
    except KeyError as exc:
        raise KeyError(f"missing key {exc}") from exc
