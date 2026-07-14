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
from pkg_job_orch.api import (
    DEV_USER_ID,
    CreditLedgerEntry,
    FunnelEvent,
    ProcessedEvent,
    User,
    balance_snapshot,
    session_scope,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

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
                    tier="free",
                )
                session.add(row)
            else:
                row.email = email
                row.tier = "free"
            session.flush()
            return row

    async def get_dev_user(self, *, email: str, tier: Tier) -> User:
        google_sub = f"dev:{email}"
        with session_scope(self._database_url) as session:
            row = session.get(User, DEV_USER_ID)
            if row is None:
                row = User(id=DEV_USER_ID, google_sub=google_sub, email=email, tier="free")
                session.add(row)
            else:
                row.google_sub = google_sub
                row.email = email
                row.tier = "free"
            session.flush()
            return row

    async def get_by_id(self, user_id: UserId) -> User | None:
        with session_scope(self._database_url) as session:
            return session.get(User, str(user_id))

    async def get_by_email(self, email: str) -> list[User]:
        with session_scope(self._database_url) as session:
            return list(session.exec(select(User).where(User.email == email)).all())

    async def apply_purchase_once(
        self,
        event_id: str,
        session_id: str,
        user_id: UserId,
        paid_at: str,
        *,
        pack: str,
        minutes: int,
        amount_cents: int,
        currency: str,
        payment_intent_id: str | None,
        charge_id: str | None,
    ) -> bool:
        """Credit a paid Checkout Session atomically, deduped by Session ID."""
        try:
            with session_scope(self._database_url) as session:
                user_id_str = str(user_id)
                user = session.get(User, user_id_str)
                if user is None:
                    logger.warning(
                        "apply_purchase_once: user %s not found; ignoring event %s",
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
                session.add(
                    CreditLedgerEntry(
                        id=uuid.uuid4().hex,
                        user_id=user_id_str,
                        entry_type="purchase",
                        minutes_delta=minutes,
                        balance_after=user.purchased_minutes + minutes,
                        idempotency_key=f"purchase:{session_id}",
                        session_id=session_id,
                        event_id=event_id,
                        pack=pack,
                        amount_cents=amount_cents,
                        currency=currency,
                        payment_intent_id=payment_intent_id,
                        charge_id=charge_id,
                        reason="Stripe Checkout purchase",
                    )
                )
                user.purchased_minutes += minutes
                user.tier = "free"
                session.add(user)
        except IntegrityError:
            return False
        return True

    async def apply_paid_webhook_once(
        self,
        event_id: str,
        session_id: str,
        user_id: UserId,
        paid_at: str,
    ) -> bool:
        """Deprecated binary-tier helper retained for API compatibility."""
        try:
            with session_scope(self._database_url) as session:
                user = session.get(User, str(user_id))
                if user is None:
                    return False
                session.add(
                    ProcessedEvent(
                        event_id=event_id,
                        session_id=session_id,
                        user_id=str(user_id),
                        paid_at=paid_at,
                    )
                )
                user.tier = "paid"
                session.add(user)
        except IntegrityError:
            return False
        return True

    async def apply_refund_once(
        self,
        *,
        event_id: str,
        refund_id: str,
        amount_cents: int,
        payment_intent_id: str | None,
        charge_id: str | None,
        reason: str | None,
        created_at: str,
    ) -> bool:
        del created_at
        return self._apply_reversal(
            event_id=event_id,
            key=f"refund:{refund_id}",
            entry_type="refund",
            amount_cents=amount_cents,
            payment_intent_id=payment_intent_id,
            charge_id=charge_id,
            reason=reason,
        )

    async def apply_dispute_once(
        self,
        *,
        event_id: str,
        dispute_id: str,
        payment_intent_id: str | None,
        charge_id: str | None,
        reason: str | None,
        reinstated: bool,
        created_at: str,
    ) -> bool:
        del created_at
        if not reinstated:
            return self._apply_reversal(
                event_id=event_id,
                key=f"dispute:{dispute_id}",
                entry_type="dispute",
                amount_cents=None,
                payment_intent_id=payment_intent_id,
                charge_id=charge_id,
                reason=reason,
            )
        try:
            with session_scope(self._database_url) as session:
                original = session.exec(
                    select(CreditLedgerEntry).where(
                        CreditLedgerEntry.idempotency_key == f"dispute:{dispute_id}"
                    )
                ).first()
                if original is None:
                    return False
                user = session.get(User, original.user_id)
                if user is None:
                    return False
                minutes = -original.minutes_delta
                session.add(
                    CreditLedgerEntry(
                        id=uuid.uuid4().hex,
                        user_id=user.id,
                        entry_type="dispute_reinstated",
                        minutes_delta=minutes,
                        balance_after=user.purchased_minutes + minutes,
                        idempotency_key=f"dispute_reinstated:{dispute_id}",
                        event_id=event_id,
                        payment_intent_id=original.payment_intent_id,
                        charge_id=original.charge_id,
                        reason=reason or "dispute funds reinstated",
                    )
                )
                user.purchased_minutes += minutes
                session.add(user)
        except IntegrityError:
            return False
        return True

    def _apply_reversal(
        self,
        *,
        event_id: str,
        key: str,
        entry_type: str,
        amount_cents: int | None,
        payment_intent_id: str | None,
        charge_id: str | None,
        reason: str | None,
    ) -> bool:
        import math

        try:
            with session_scope(self._database_url) as session:
                purchase = self._find_purchase(session, payment_intent_id, charge_id)
                if purchase is None or purchase.amount_cents is None:
                    return False
                user = session.get(User, purchase.user_id)
                if user is None:
                    return False
                requested = (
                    purchase.minutes_delta
                    if amount_cents is None
                    else math.ceil(amount_cents / purchase.amount_cents * purchase.minutes_delta)
                )
                related = session.exec(
                    select(CreditLedgerEntry).where(
                        CreditLedgerEntry.user_id == purchase.user_id,
                        CreditLedgerEntry.payment_intent_id == purchase.payment_intent_id,
                    )
                ).all()
                net_reversed = -sum(
                    row.minutes_delta
                    for row in related
                    if row.entry_type in {"refund", "dispute", "dispute_reinstated"}
                )
                minutes = min(requested, max(0, purchase.minutes_delta - net_reversed))
                session.add(
                    CreditLedgerEntry(
                        id=uuid.uuid4().hex,
                        user_id=purchase.user_id,
                        entry_type=entry_type,
                        minutes_delta=-minutes,
                        balance_after=user.purchased_minutes - minutes,
                        idempotency_key=key,
                        event_id=event_id,
                        pack=purchase.pack,
                        amount_cents=amount_cents,
                        currency=purchase.currency,
                        payment_intent_id=purchase.payment_intent_id,
                        charge_id=purchase.charge_id,
                        reason=reason,
                    )
                )
                user.purchased_minutes -= minutes
                session.add(user)
        except IntegrityError:
            return False
        return True

    @staticmethod
    def _find_purchase(
        session: Session,
        payment_intent_id: str | None,
        charge_id: str | None,
    ) -> CreditLedgerEntry | None:
        stmt = select(CreditLedgerEntry).where(CreditLedgerEntry.entry_type == "purchase")
        if payment_intent_id is not None:
            stmt = stmt.where(CreditLedgerEntry.payment_intent_id == payment_intent_id)
        elif charge_id is not None:
            stmt = stmt.where(CreditLedgerEntry.charge_id == charge_id)
        else:
            return None
        return session.exec(stmt).first()

    async def balance(self, user_id: UserId, free_limit: int) -> dict[str, int]:
        with session_scope(self._database_url) as session:
            value = balance_snapshot(session, str(user_id), free_limit)
            return {
                "free_limit": value.free_limit,
                "free_used": value.free_used,
                "free_remaining": value.free_remaining,
                "purchased_minutes": value.purchased_minutes,
                "available_minutes": value.available_minutes,
            }

    async def record_checkout_started(self, user_id: UserId, pack: str) -> None:
        with session_scope(self._database_url) as session:
            session.add(
                FunnelEvent(
                    id=uuid.uuid4().hex,
                    user_id=str(user_id),
                    event_type="checkout_started",
                    pack=pack,
                )
            )

    async def has_processed_event(self, event_id: str) -> bool:
        with session_scope(self._database_url) as session:
            return session.get(ProcessedEvent, event_id) is not None

    async def usage_count_this_period(self, user_id: UserId) -> int:
        return self._usage_this_period.get(str(user_id), 0)
