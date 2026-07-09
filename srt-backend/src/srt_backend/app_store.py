"""Shared DB-backed app store for auth and billing.

Implements both ``UserStore`` (pkg-auth) and ``BillingStore`` (pkg-billing)
against the canonical ``pkg_job_orch`` DB. ``User`` is the job-orch
SQLModel row (Phase 0 #2 / Phase 3 #9); ``session_scope`` uses
``expire_on_commit=False`` so callers can read attributes after the
session closes — no detached value type is needed.
"""

from __future__ import annotations

import logging
import uuid

from pkg_auth.api import UserStore
from pkg_auth.models import Tier
from pkg_billing.api import BillingStore, UserId
from pkg_job_orch.api import DEV_USER_ID, ProcessedEvent, User, session_scope
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

__all__ = ["AppStore"]

logger = logging.getLogger(__name__)


class AppStore(UserStore, BillingStore):
    """SQLite-backed store shared by pkg-auth and pkg-billing."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url
        self._usage_this_period: dict[str, int] = {}

    async def get_by_sub(self, google_sub: str) -> User | None:
        with session_scope(self._database_url) as session:
            row = session.exec(select(User).where(User.google_sub == google_sub)).first()
            return row if row is not None else None

    async def upsert(self, *, google_sub: str, email: str, tier: Tier = "free") -> User:
        with session_scope(self._database_url) as session:
            row = session.exec(select(User).where(User.google_sub == google_sub)).first()
            if row is None:
                row = User(
                    id=uuid.uuid4().hex,
                    google_sub=google_sub,
                    email=email,
                    tier=tier,
                )
                session.add(row)
            else:
                row.email = email
                # Sticky-paid: never downgrade a paid user on re-upsert.
                row.tier = "paid" if row.tier == "paid" and tier == "free" else tier
            session.flush()
            return row

    async def get_dev_user(self, *, email: str, tier: Tier) -> User:
        google_sub = f"dev:{email}"
        with session_scope(self._database_url) as session:
            row = session.get(User, DEV_USER_ID)
            if row is None:
                row = User(id=DEV_USER_ID, google_sub=google_sub, email=email, tier=tier)
                session.add(row)
            else:
                row.google_sub = google_sub
                row.email = email
                row.tier = "paid" if row.tier == "paid" and tier == "free" else tier
            session.flush()
            return row

    async def get_by_id(self, user_id: UserId) -> User | None:
        with session_scope(self._database_url) as session:
            return session.get(User, str(user_id))

    async def get_by_email(self, email: str) -> list[User]:
        with session_scope(self._database_url) as session:
            return list(session.exec(select(User).where(User.email == email)).all())

    async def apply_paid_webhook_once(
        self,
        event_id: str,
        session_id: str,
        user_id: UserId,
        paid_at: str,
    ) -> bool:
        """Insert the processed-event row and flip the user to paid in one txn.

        The unique PK on ``processed_events.event_id`` is the dedupe guard:
        a duplicate insert raises ``IntegrityError`` and the whole txn rolls
        back, so the tier is never flipped without recording the event (and
        vice-versa). Returns ``False`` if the event was already recorded.
        """
        try:
            with session_scope(self._database_url) as session:
                user_id_str = str(user_id)
                user = session.get(User, user_id_str)
                if user is None:
                    logger.warning(
                        "apply_paid_webhook_once: user %s not found; ignoring event %s",
                        user_id_str,
                        event_id,
                    )
                    return False
                session.add(
                    ProcessedEvent(
                        event_id=event_id,
                        session_id=session_id,
                        user_id=user_id_str,
                        paid_at=paid_at,
                    )
                )
                user.tier = "paid"
                session.add(user)
        except IntegrityError:
            return False
        return True

    async def has_processed_event(self, event_id: str) -> bool:
        with session_scope(self._database_url) as session:
            return session.get(ProcessedEvent, event_id) is not None

    async def usage_count_this_period(self, user_id: UserId) -> int:
        return self._usage_this_period.get(str(user_id), 0)
