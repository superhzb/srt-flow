"""Job orchestration: enqueue, worker_loop, recover, seed dev user.

Pure-ish wiring layer over models/db/storage/worker_client. The app
lifespan constructs the queue + worker_loop task and shares them via
``app.state``; the router calls :func:`enqueue` with that queue.

Single-writer invariant: exactly one ``worker_loop`` per process pulls
``concurrency=1``. SQLite's single writer + the mlx worker's
single-threaded model both demand it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from pkg_file_upload.api import Storage
from pkg_srt_services.api import Cue, parse, serialize
from sqlmodel import Session, col, select

from .config import DEFAULT_DEV_USER_EMAIL, load_settings
from .db import session_scope
from .models import Job, User, tgt_langs_from_csv, tgt_langs_to_csv
from .worker_client import (
    StreamOutcome,
    WorkerStreamError,
    build_segments,
    stream_translate,
)
from .workers import WorkerResolutionError, worker_base_url

__all__ = [
    "DEFAULT_DEV_USER_EMAIL",
    "DEV_USER_ID",
    "EnqueueError",
    "EnqueueResult",
    "JobContext",
    "Notifier",
    "NullNotifier",
    "WorkerClientFn",
    "default_worker_client",
    "enqueue",
    "recover_jobs",
    "seed_dev_user",
    "worker_loop",
]

logger = logging.getLogger(__name__)

# The dev user owns every slice-3 job. A fixed synthetic id keeps test
# assertions stable; slice 4 swaps this for real OAuth upserts.
DEV_USER_ID = "dev-user"

# Polling cadence on an empty queue — keeps the loop responsive to the
# shutdown signal without busy-spinning.
_QUEUE_POLL_TIMEOUT: float = 0.5


class EnqueueError(ValueError):
    """Raised when a job cannot be enqueued (bad worker, bad cues, …)."""


@dataclass(frozen=True)
class EnqueueResult:
    job_id: str
    job: Job


class Notifier(Protocol):
    """Notification seam — stubbed (no-op) until slice 6."""

    def notify_done(self, job_id: str) -> None: ...
    def notify_failed(self, job_id: str, error: str) -> None: ...


class NullNotifier:
    """Default notifier — does nothing. Slice 6 wires a real one."""

    def notify_done(self, job_id: str) -> None:
        del job_id

    def notify_failed(self, job_id: str, error: str) -> None:
        del job_id, error


# The streaming worker call, isolated for test patching. ``worker_loop``
# reads this name lazily so tests can monkeypatch ``orchestration._worker_client``.
WorkerClientFn = Callable[
    [str, str, list[str], list[dict[str, Any]], "Callable[[float], None] | None"],
    "Any",
]


async def default_worker_client(
    base_url: str,
    source_lang: str,
    targets: list[str],
    segments: list[dict[str, Any]],
    on_progress: Callable[[float], None] | None,
) -> StreamOutcome:
    return await stream_translate(base_url, source_lang, targets, segments, on_progress)


@dataclass
class JobContext:
    """Bundle of shared services passed to ``worker_loop``.

    Lives on ``app.state`` so routes and the loop share the same queue,
    storage, and notifier. Constructed once by the lifespan.
    """

    queue: asyncio.Queue[str]
    storage: Storage
    dev_user_id: str
    notifier: Notifier
    # Patchable seam: tests swap this for a fake. Real code uses
    # ``default_worker_client``. Default assigned in __post_init__ to
    # sidestep dataclass field-default-vs-factory awkwardness.
    worker_client: WorkerClientFn | None = None

    def __post_init__(self) -> None:
        if self.worker_client is None:
            self.worker_client = default_worker_client


def seed_dev_user(
    session: Session,
    email: str | None = None,
    tier: str | None = None,
    user_id: str = DEV_USER_ID,
) -> User:
    """Idempotently upsert the seeded dev user. Returns the row.

    Called from the lifespan on startup. ``email``/``tier`` default to
    env (``DEV_USER_EMAIL`` / ``DEV_USER_TIER``) or sane defaults.
    """
    settings = load_settings()
    email = email or settings.dev_user_email
    tier = tier or settings.dev_user_tier
    existing = session.get(User, user_id)
    if existing is not None:
        return existing
    user = User(id=user_id, email=email, tier=tier)
    session.add(user)
    session.flush()
    return user


def enqueue(
    ctx: JobContext,
    session: Session,
    *,
    cues: list[Cue],
    source_lang: str,
    targets: list[str],
    worker_id: str,
) -> EnqueueResult:
    """Persist a new pending job and put its id on the queue.

    Steps (PLAN.md slice 3, "Accept + persist"):
      1. Resolve the worker id → base URL (fails fast on unknown worker).
      2. Serialize cues → input.srt text → Storage.save.
      3. INSERT job(pending).
      4. Queue the id for the worker_loop (volatile; durability = the row).

    The session is committed by the caller (the route) — this keeps the
    enqueue + queue.put in one transaction. If commit fails the queue
    still has nothing to consume (consumer re-checks status from DB).
    """
    if not cues:
        raise EnqueueError("at least one cue is required")
    if not source_lang:
        raise EnqueueError("source_lang is required")
    if not targets:
        raise EnqueueError("at least one target language is required")

    # Dedup targets, drop the source if it slipped in, preserve order.
    seen: set[str] = set()
    clean_targets: list[str] = []
    for t in targets:
        if t == source_lang or t in seen or not t:
            continue
        seen.add(t)
        clean_targets.append(t)
    if not clean_targets:
        raise EnqueueError("at least one target language is required (after dedup)")

    # Resolve worker eagerly — 404 belongs to the POST, not the worker_loop.
    try:
        base_url = worker_base_url(worker_id)
    except WorkerResolutionError as exc:
        raise EnqueueError(str(exc)) from exc

    job_id = uuid.uuid4().hex
    input_srt = serialize(cues)
    ctx.storage.save(
        ctx.dev_user_id, job_id, "input.srt", input_srt.encode("utf-8")
    )

    job = Job(
        id=job_id,
        user_id=ctx.dev_user_id,
        status="pending",
        worker=worker_id,
        src_lang=source_lang,
        tgt_langs=tgt_langs_to_csv(clean_targets),
        progress=0.0,
    )
    session.add(job)
    session.flush()
    # base_url is unused here but validated above — keeps the failure on the
    # request boundary. The worker_loop resolves it again from job.worker.
    del base_url
    return EnqueueResult(job_id=job_id, job=job)


def recover_jobs(session: Session) -> int:
    """Restart recovery — reset ``processing`` → ``pending``.

    Also no-op for ``done``/``failed`` rows. Returns the number of rows
    reset (diagnostic). Callers re-enqueue every ``pending`` row after
    this; see :func:`enqueue_pending`.
    """
    stmt = select(Job).where(Job.status == "processing")
    reset = 0
    for job in session.exec(stmt).all():
        job.status = "pending"
        job.progress = 0.0
        job.error = None
        session.add(job)
        reset += 1
    return reset


def list_pending(session: Session) -> list[Job]:
    """All jobs in ``pending`` status, oldest first (FIFO)."""
    stmt = select(Job).where(Job.status == "pending").order_by(col(Job.created_at))
    return list(session.exec(stmt).all())


async def worker_loop(ctx: JobContext, stop_event: asyncio.Event) -> None:
    """Pull job ids off the queue, process one at a time, until stopped.

    Failure isolation: a single job's exception is caught and logged —
    the loop survives. The shutdown path sets ``stop_event`` and the
    next poll iteration exits.
    """
    logger.info("worker_loop started")
    while not stop_event.is_set():
        try:
            job_id = await asyncio.wait_for(
                ctx.queue.get(), timeout=_QUEUE_POLL_TIMEOUT
            )
        except TimeoutError:
            continue
        try:
            await _process_job(ctx, job_id)
        except Exception:
            # _process_job already records failures on the Job row; this
            # is a belt-and-braces guard so the loop can never die.
            logger.exception("worker_loop: unhandled error on job %s", job_id)
    logger.info("worker_loop stopped")


async def _process_job(ctx: JobContext, job_id: str) -> None:
    """Claim one job, stream-translate, land results / failure on the DB."""
    # Phase 1: claim. Capture the primitives we need outside this session —
    # the Job instance goes detached on session close.
    with session_scope() as session:
        job = session.get(Job, job_id)
        if job is None:
            logger.warning("worker_loop: queue held unknown job %s; dropping", job_id)
            return
        if job.status != "pending":
            logger.info(
                "worker_loop: job %s in status %s — skipping", job_id, job.status
            )
            return
        job.status = "processing"
        session.add(job)
        session.commit()
        session.refresh(job)
        worker = job.worker
        src_lang = job.src_lang
        targets = tgt_langs_from_csv(job.tgt_langs)

    try:
        outcome = await _run_translation(ctx, job_id, worker, src_lang, targets)
    except WorkerStreamError as exc:
        _mark_failed(job_id, str(exc))
        ctx.notifier.notify_failed(job_id, str(exc))
        return
    except Exception as exc:  # noqa: BLE001 — never let the worker_loop die
        logger.exception("worker_loop: translation crashed for job %s", job_id)
        _mark_failed(job_id, f"internal error: {exc}")
        ctx.notifier.notify_failed(job_id, f"internal error: {exc}")
        return

    # All-or-nothing: write all outputs, then flip status=done in one tx.
    try:
        _land_results(ctx, job_id, outcome)
    except Exception as exc:  # noqa: BLE001
        logger.exception("worker_loop: landing results failed for job %s", job_id)
        _mark_failed(job_id, f"failed to land results: {exc}")
        ctx.notifier.notify_failed(job_id, f"failed to land results: {exc}")


async def _run_translation(
    ctx: JobContext,
    job_id: str,
    worker: str,
    src_lang: str,
    targets: list[str],
) -> StreamOutcome:
    """Resolve worker, parse input.srt → cues, stream-translate."""
    base_url = worker_base_url(worker)
    raw_input = ctx.storage.get(ctx.dev_user_id, job_id, "input.srt")
    cues = parse(raw_input.decode("utf-8"))
    segments = build_segments(cues, src_lang)

    def on_progress(fraction: float) -> None:
        # Sync DB write inside an async callback — SQLite is fast; the
        # event loop briefly blocks. Acceptable at slice-3 volume.
        try:
            with session_scope() as session:
                row = session.get(Job, job_id)
                if row is not None and row.status == "processing":
                    row.progress = float(fraction)
                    session.add(row)
        except Exception:  # noqa: BLE001 — progress write must not kill the job
            logger.warning("worker_loop: progress write failed for %s", job_id)

    client = ctx.worker_client
    assert client is not None  # __post_init__ guarantees this
    result = await client(base_url, src_lang, targets, segments, on_progress)
    if isinstance(result, StreamOutcome):
        return result
    # Tests may pass a fake returning a plain dict — coerce for symmetry.
    return StreamOutcome(
        source_lang=str(result.get("source_lang", src_lang)),
        targets=list(result.get("targets", targets)),
        segments=list(result.get("segments", [])),
    )


def _land_results(ctx: JobContext, job_id: str, outcome: StreamOutcome) -> None:
    """Write one output.<lang>.srt per target, then mark the job done."""
    cues = parse(ctx.storage.get(ctx.dev_user_id, job_id, "input.srt").decode("utf-8"))
    outputs = _build_outputs(cues, outcome)

    for lang, srt_text in outputs.items():
        ctx.storage.save(
            ctx.dev_user_id,
            job_id,
            f"output.{lang}.srt",
            srt_text.encode("utf-8"),
        )

    with session_scope() as session:
        row = session.get(Job, job_id)
        if row is None:
            logger.error("worker_loop: job %s vanished before landing", job_id)
            return
        row.status = "done"
        row.progress = 1.0
        row.error = None
        row.finished_at = datetime.now(UTC)
        session.add(row)
        session.commit()
    ctx.notifier.notify_done(job_id)


def _mark_failed(job_id: str, message: str) -> None:
    try:
        with session_scope() as session:
            row = session.get(Job, job_id)
            if row is None:
                return
            row.status = "failed"
            row.error = message
            row.finished_at = datetime.now(UTC)
            session.add(row)
    except Exception:  # noqa: BLE001 — never raise from failure path
        logger.exception("worker_loop: failed to mark job %s as failed", job_id)


def _build_outputs(
    cues: list[Cue], outcome: StreamOutcome
) -> dict[str, str]:
    """Per-target SRT: clone cues, swap text with translated text by id."""
    by_id: dict[int, dict[str, Any]] = {
        int(seg["id"]): seg for seg in outcome.segments if "id" in seg
    }
    outputs: dict[str, str] = {}
    for tgt in outcome.targets:
        translated: list[Cue] = []
        for cue in cues:
            entry = by_id.get(cue.index)
            text = entry.get(tgt) if entry else None
            if isinstance(text, str):
                translated.append(Cue(cue.index, cue.start, cue.end, text))
            else:
                translated.append(cue)
        outputs[tgt] = serialize(translated)
    return outputs


def enqueue_pending(ctx: JobContext, session: Session) -> int:
    """Put every pending job id on the queue (boot-time replay)."""
    count = 0
    for job in list_pending(session):
        ctx.queue.put_nowait(job.id)
        count += 1
    return count
