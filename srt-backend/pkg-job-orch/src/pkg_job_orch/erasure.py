"""User data erasure (right to be forgotten).

Deletes everything that identifies a person and everything they uploaded:
the ``User`` row (email, google_sub), all their ``Job`` rows and on-disk
artifacts, and the identity fields on their analytics ``Event`` rows.

Financial rows (``credit_ledger``, ``processed_events``) are deliberately
retained for tax/accounting and Stripe reconciliation. After the ``User`` row
is gone they reference only an opaque, now-orphaned user id — no personal data
remains. This mirrors the GDPR/Law 25 carve-out for records a controller must
keep to meet a legal obligation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pkg_file_upload.api import Storage
from sqlmodel import Session, select

from .models import Event, Job, User

__all__ = ["ErasureResult", "erase_user"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ErasureResult:
    """Counts of what an erasure removed/anonymized, for logging and response."""

    user_deleted: bool
    jobs_deleted: int
    events_anonymized: int


def erase_user(session: Session, storage: Storage, user_id: str) -> ErasureResult:
    """Erase a user's identity + content. Idempotent (re-running is a no-op).

    Order: remove job rows and disk artifacts, anonymize analytics events, then
    delete the user row last. No FK cascade exists (SQLite enforcement off), so
    child rows are handled explicitly.
    """
    jobs = session.exec(select(Job).where(Job.user_id == user_id)).all()
    for job in jobs:
        session.delete(job)
    # Remove the whole user tree in one shot (covers any orphaned job dirs too).
    storage.delete_user(user_id)

    events = session.exec(select(Event).where(Event.user_id == user_id)).all()
    for event in events:
        event.user_id = None
        event.anon_id = None
        session.add(event)

    user = session.get(User, user_id)
    if user is not None:
        session.delete(user)

    logger.info(
        "erased user %s: %d jobs, %d events anonymized, user_row=%s",
        user_id,
        len(jobs),
        len(events),
        user is not None,
    )
    return ErasureResult(
        user_deleted=user is not None,
        jobs_deleted=len(jobs),
        events_anonymized=len(events),
    )
