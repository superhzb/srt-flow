"""Data-retention purge: delete uploaded artifacts + job rows past their TTL.

Uploaded SRT files and their translations are kept only long enough to be
useful, then removed — both the on-disk artifacts (``{root}/{user_id}/{job_id}/``)
and the ``Job`` row. Analytics events are anonymized at their own (longer)
horizon via :func:`anonymize_old_events`. Financial rows (``credit_ledger``,
``processed_events``) are intentionally *not* touched here: they are retained
for tax/accounting and Stripe reconciliation, keyed by an opaque user id.

The scheduling loop (:func:`retention_loop`) is started by the app lifespan
alongside ``worker_loop`` and mirrors its clean-shutdown handling.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from pkg_file_upload.api import Storage
from sqlmodel import Session, col, select

from .db import session_scope
from .events import DEFAULT_RETENTION_DAYS, anonymize_old_events
from .models import Job

__all__ = [
    "DEFAULT_JOB_RETENTION_DAYS",
    "DEFAULT_RETENTION_INTERVAL_SECONDS",
    "purge_old_jobs",
    "run_retention_pass",
    "retention_loop",
]

logger = logging.getLogger(__name__)

# Uploaded subtitles + outputs are short-lived; users download soon after a job
# finishes. 30 days is comfortably longer than that while bounding how long any
# user content sits on disk.
DEFAULT_JOB_RETENTION_DAYS = 30

# How often the purge loop runs. Daily is ample — retention is measured in days.
DEFAULT_RETENTION_INTERVAL_SECONDS = 24 * 60 * 60


def purge_old_jobs(
    session: Session,
    storage: Storage,
    *,
    retention_days: int = DEFAULT_JOB_RETENTION_DAYS,
    now: datetime | None = None,
) -> int:
    """Delete jobs (row + on-disk artifacts) created before the retention horizon.

    Returns the number of jobs purged. The on-disk directory is removed first;
    ``delete_job`` treats a missing directory as a no-op, so a partially-cleaned
    job still converges. Financial ledger rows referencing the job id are left
    intact for audit.
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    stmt = select(Job).where(col(Job.created_at) < cutoff)
    count = 0
    for job in session.exec(stmt).all():
        storage.delete_job(job.user_id, job.id)
        session.delete(job)
        count += 1
    return count


def run_retention_pass(
    storage: Storage,
    *,
    job_retention_days: int = DEFAULT_JOB_RETENTION_DAYS,
    event_retention_days: int = DEFAULT_RETENTION_DAYS,
    database_url: str | None = None,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Run one full retention pass in its own transaction.

    Purges old jobs and anonymizes old analytics events. Returns
    ``(jobs_purged, events_anonymized)``.
    """
    with session_scope(database_url) as session:
        jobs = purge_old_jobs(session, storage, retention_days=job_retention_days, now=now)
        events = anonymize_old_events(session, retention_days=event_retention_days, now=now)
    return jobs, events


async def retention_loop(
    storage: Storage,
    stop_event: asyncio.Event,
    *,
    interval_seconds: int = DEFAULT_RETENTION_INTERVAL_SECONDS,
    job_retention_days: int = DEFAULT_JOB_RETENTION_DAYS,
    event_retention_days: int = DEFAULT_RETENTION_DAYS,
    database_url: str | None = None,
) -> None:
    """Run a retention pass now, then every ``interval_seconds`` until stopped.

    Failure isolation mirrors ``worker_loop``: a pass that raises is logged and
    the loop survives to try again next interval. Shutdown sets ``stop_event``
    and the next wait returns immediately.
    """
    logger.info(
        "retention_loop started (jobs>%dd, events>%dd, every %ds)",
        job_retention_days,
        event_retention_days,
        interval_seconds,
    )
    while True:
        try:
            jobs, events = run_retention_pass(
                storage,
                job_retention_days=job_retention_days,
                event_retention_days=event_retention_days,
                database_url=database_url,
            )
            if jobs or events:
                logger.info(
                    "retention pass: purged %d jobs, anonymized %d events",
                    jobs,
                    events,
                )
        except Exception:
            logger.exception("retention pass failed; will retry next interval")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue
        break
    logger.info("retention_loop stopped")
