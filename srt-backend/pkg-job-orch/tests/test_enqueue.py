"""Tests for enqueue(), seed_dev_user(), recover_jobs(), worker_loop()."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pkg_srt_services.api import Cue
from sqlmodel import Session, select

from pkg_job_orch.api import (
    DEV_USER_ID,
    EnqueueError,
    EnqueueResult,
    Job,
    JobContext,
    StreamOutcome,
    User,
    WorkerStreamError,
    default_worker_client,
    enqueue,
    enqueue_pending,
    get_engine,
    recover_jobs,
    seed_dev_user,
    worker_loop,
)


def _cues() -> list[Cue]:
    return [Cue(index=1, start="00:00:01,000", end="00:00:02,000", text="Hello")]


def test_seed_dev_user_idempotent(temp_db: str) -> None:
    with Session(get_engine()) as s:
        u1 = seed_dev_user(s)
        u1_id = u1.id
        s.commit()
    with Session(get_engine()) as s:
        u2 = seed_dev_user(s)
        u2_id = u2.id
        s.commit()
    assert u1_id == u2_id == DEV_USER_ID
    with Session(get_engine()) as s:
        rows = s.exec(select(User)).all()
    assert len(rows) == 1


def test_enqueue_persists_pending_and_input(
    temp_db: str, job_ctx: JobContext
) -> None:
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.commit()
    with Session(get_engine()) as s:
        result = enqueue(
            job_ctx,
            s,
            cues=_cues(),
            source_lang="en",
            targets=["fr", "de"],
            worker_id="mlx",
        )
        job_id = result.job_id
        inner_id = result.job.id
        tgt_csv = result.job.tgt_langs
        worker = result.job.worker
        status = result.job.status
        s.commit()
    assert isinstance(result, EnqueueResult)
    assert job_id == inner_id
    assert status == "pending"
    assert tgt_csv == "fr,de"
    assert worker == "mlx"

    # input.srt landed on disk in the canonical layout.
    saved = job_ctx.storage.get(DEV_USER_ID, job_id, "input.srt")
    assert saved == b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
    # The row is in pending — the route is what puts the id on the queue
    # (enqueue persists but does not schedule; that's a route-layer concern).
    with Session(get_engine()) as s:
        row = s.get(Job, job_id)
    assert row is not None
    assert row.status == "pending"


def test_enqueue_rejects_unknown_worker(temp_db: str, job_ctx: JobContext) -> None:
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.commit()
    with Session(get_engine()) as s:
        with pytest.raises(EnqueueError, match="unknown worker"):
            enqueue(
                job_ctx,
                s,
                cues=_cues(),
                source_lang="en",
                targets=["fr"],
                worker_id="ghost",
            )


def test_enqueue_dedupes_and_drops_source(
    temp_db: str, job_ctx: JobContext
) -> None:
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.commit()
    with Session(get_engine()) as s:
        result = enqueue(
            job_ctx,
            s,
            cues=_cues(),
            source_lang="en",
            targets=["fr", "fr", "en", "de"],
            worker_id="mlx",
        )
        tgt_csv = result.job.tgt_langs
        s.commit()
    assert tgt_csv == "fr,de"


def test_enqueue_rejects_empty_targets(temp_db: str, job_ctx: JobContext) -> None:
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.commit()
    with Session(get_engine()) as s:
        with pytest.raises(EnqueueError):
            enqueue(
                job_ctx, s, cues=_cues(), source_lang="en", targets=[], worker_id="mlx"
            )


def test_recover_resets_processing_to_pending(temp_db: str) -> None:
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.add(Job(id="p1", user_id=DEV_USER_ID, worker="mlx", src_lang="en",
                  status="processing", progress=0.4))
        s.add(Job(id="p2", user_id=DEV_USER_ID, worker="mlx", src_lang="en",
                  status="pending"))
        s.add(Job(id="d1", user_id=DEV_USER_ID, worker="mlx", src_lang="en",
                  status="done", progress=1.0))
        s.commit()
    with Session(get_engine()) as s:
        reset_count = recover_jobs(s)
        s.commit()
    assert reset_count == 1
    with Session(get_engine()) as s:
        p1 = s.get(Job, "p1")
        assert p1 is not None
        assert p1.status == "pending"
        assert p1.progress == 0.0
        assert p1.error is None
        # done row untouched
        d1 = s.get(Job, "d1")
        assert d1 is not None
        assert d1.status == "done"


def test_enqueue_pending_replays_all(temp_db: str, job_ctx: JobContext) -> None:
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.add(Job(id="p1", user_id=DEV_USER_ID, worker="mlx", src_lang="en"))
        s.add(Job(id="p2", user_id=DEV_USER_ID, worker="mlx", src_lang="en"))
        s.commit()
    with Session(get_engine()) as s:
        n = enqueue_pending(job_ctx, s)
    assert n == 2
    assert job_ctx.queue.qsize() == 2


async def test_worker_loop_processes_job_to_done(
    temp_db: str, job_ctx: JobContext, fake_worker_client: Any
) -> None:
    """End-to-end through the loop: enqueue → process → done + output file."""
    job_ctx.worker_client = fake_worker_client  # type: ignore[method-assign]
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.commit()
    with Session(get_engine()) as s:
        result = enqueue(
            job_ctx,
            s,
            cues=_cues(),
            source_lang="en",
            targets=["fr", "de"],
            worker_id="mlx",
        )
        s.commit()
    job_ctx.queue.put_nowait(result.job_id)

    stop = asyncio.Event()
    task = asyncio.create_task(worker_loop(job_ctx, stop))
    # Wait for the job to reach a terminal state.
    for _ in range(50):
        with Session(get_engine()) as s:
            job = s.get(Job, result.job_id)
            if job and job.status in {"done", "failed"}:
                break
        await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=2.0)

    with Session(get_engine()) as s:
        job = s.get(Job, result.job_id)
    assert job is not None
    assert job.status == "done", f"error: {job.error}"
    assert job.progress == 1.0
    # Two output files written.
    fr = job_ctx.storage.get(DEV_USER_ID, result.job_id, "output.fr.srt")
    de = job_ctx.storage.get(DEV_USER_ID, result.job_id, "output.de.srt")
    assert b"[fr] Hello" in fr
    assert b"[de] Hello" in de
    # Worker client was called with the right segments.
    assert len(fake_worker_client.calls) == 1
    call = fake_worker_client.calls[0]
    assert call["source_lang"] == "en"
    assert call["targets"] == ["fr", "de"]
    assert call["segments"] == [{"id": 1, "en": "Hello"}]


async def test_worker_loop_marks_failed_on_worker_error(
    temp_db: str, job_ctx: JobContext
) -> None:
    job_ctx.worker_client = _RaisingClient(WorkerStreamError("boom"))  # type: ignore[method-assign]
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.commit()
    with Session(get_engine()) as s:
        result = enqueue(
            job_ctx, s, cues=_cues(), source_lang="en", targets=["fr"], worker_id="mlx"
        )
        s.commit()
    job_ctx.queue.put_nowait(result.job_id)

    stop = asyncio.Event()
    task = asyncio.create_task(worker_loop(job_ctx, stop))
    for _ in range(50):
        with Session(get_engine()) as s:
            job = s.get(Job, result.job_id)
            if job and job.status in {"done", "failed"}:
                break
        await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=2.0)

    with Session(get_engine()) as s:
        job = s.get(Job, result.job_id)
    assert job is not None
    assert job.status == "failed"
    assert "boom" in (job.error or "")
    # No output files for a failed job.
    import pytest as _pt
    from pkg_file_upload.api import StorageError

    with _pt.raises(StorageError):
        job_ctx.storage.get(DEV_USER_ID, result.job_id, "output.fr.srt")


async def test_worker_loop_survives_restart(temp_db: str, job_ctx: JobContext) -> None:
    """Simulate restart: processing job → recover → loop picks it up → done."""
    job_ctx.worker_client = _SuccessClient()  # type: ignore[method-assign]
    with Session(get_engine()) as s:
        seed_dev_user(s)
        s.commit()
    # Persist input.srt manually (simulating a job that was enqueued then killed).
    with Session(get_engine()) as s:
        result = enqueue(
            job_ctx, s, cues=_cues(), source_lang="en", targets=["fr"], worker_id="mlx"
        )
        s.commit()
    # Simulate crash mid-flight: flip status to processing manually.
    with Session(get_engine()) as s:
        job = s.get(Job, result.job_id)
        assert job is not None
        job.status = "processing"
        job.progress = 0.3
        s.add(job)
        s.commit()

    # Restart path: recover + enqueue_pending + run loop.
    with Session(get_engine()) as s:
        recover_jobs(s)
        s.commit()
    with Session(get_engine()) as s:
        enqueue_pending(job_ctx, s)

    stop = asyncio.Event()
    task = asyncio.create_task(worker_loop(job_ctx, stop))
    for _ in range(50):
        with Session(get_engine()) as s:
            job = s.get(Job, result.job_id)
            if job and job.status in {"done", "failed"}:
                break
        await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=2.0)

    with Session(get_engine()) as s:
        job = s.get(Job, result.job_id)
    assert job is not None
    assert job.status == "done"
    assert job_ctx.storage.get(DEV_USER_ID, result.job_id, "output.fr.srt") is not None


class _RaisingClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise self._exc


class _SuccessClient:
    async def __call__(
        self,
        base_url: str,
        source_lang: str,
        targets: list[str],
        segments: list[dict[str, Any]],
        on_progress: Any,
    ) -> StreamOutcome:
        if on_progress is not None:
            on_progress(1.0)
        return StreamOutcome(
            source_lang=source_lang,
            targets=targets,
            segments=[
                {"id": seg["id"], **{t: f"[{t}] {seg[source_lang]}" for t in targets}}
                for seg in segments
            ],
        )


# Reference import — keeps default_worker_client in the public surface even
# if no test calls it directly.
_ = default_worker_client
