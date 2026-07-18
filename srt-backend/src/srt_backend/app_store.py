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
from datetime import datetime

from pkg_auth.api import UserStore
from pkg_auth.models import Tier
from pkg_billing.api import BillingStore, LedgerCursor, UserId
from pkg_job_orch.api import (
    DEV_USER_ID,
    CreditLedgerEntry,
    ProcessedEvent,
    User,
    balance_snapshot,
    record_event,
    session_scope,
)
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

__all__ = ["AppStore"]

logger = logging.getLogger(__name__)


class AppStore(UserStore, BillingStore):
    """SQLite-backed store shared by pkg-auth and pkg-billing."""

    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = database_url

    async def get_by_sub(self, google_sub: str) -> User | None:
        with session_scope(self._database_url) as session:
            row = session.exec(select(User).where(User.google_sub == google_sub)).first()
            return row if row is not None else None

    async def upsert(self, *, google_sub: str, email: str, tier: Tier = "free") -> User:
        with session_scope(self._database_url) as session:
            row = session.exec(select(User).where(User.google_sub == google_sub)).first()
            created = row is None
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
            # First upsert = sign-up (once ever, keyed on user_id); every later
            # one is a login (distinct each time, so no dedup key).
            if created:
                record_event(
                    session,
                    "user_signed_up",
                    user_id=row.id,
                    dedup_key=row.id,
                    props={"provider": "google"},
                )
            else:
                record_event(
                    session,
                    "user_logged_in",
                    user_id=row.id,
                    props={"provider": "google"},
                )
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
                ledger_entry_id = uuid.uuid4().hex
                session.add(
                    CreditLedgerEntry(
                        id=ledger_entry_id,
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
                        created_at=datetime.fromisoformat(paid_at),
                    )
                )
                user.purchased_minutes += minutes
                user.tier = "free"
                session.add(user)
                # Keyed on the Stripe event_id — the same idempotency the
                # ProcessedEvent row enforces, so the fact lands at most once.
                record_event(
                    session,
                    "purchase_completed",
                    user_id=user_id_str,
                    dedup_key=event_id,
                    props={"pack": pack, "ledger_entry_id": ledger_entry_id},
                )
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
        return self._apply_reversal(
            event_id=event_id,
            key=f"refund:{refund_id}",
            entry_type="refund",
            amount_cents=amount_cents,
            payment_intent_id=payment_intent_id,
            charge_id=charge_id,
            reason=reason,
            created_at=datetime.fromisoformat(created_at),
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
        event_created_at = datetime.fromisoformat(created_at)
        if not reinstated:
            return self._apply_reversal(
                event_id=event_id,
                key=f"dispute:{dispute_id}",
                entry_type="dispute",
                amount_cents=None,
                payment_intent_id=payment_intent_id,
                charge_id=charge_id,
                reason=reason,
                created_at=event_created_at,
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
                        created_at=event_created_at,
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
        created_at: datetime,
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
                        created_at=created_at,
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

    async def list_ledger(
        self,
        user_id: UserId,
        limit: int,
        cursor: LedgerCursor | None = None,
        entry_types: frozenset[str] | None = None,
    ) -> list[CreditLedgerEntry]:
        with session_scope(self._database_url) as session:
            stmt = select(CreditLedgerEntry).where(
                CreditLedgerEntry.user_id == str(user_id),
                ~and_(
                    col(CreditLedgerEntry.entry_type) == "job_debit",
                    col(CreditLedgerEntry.minutes_delta) == 0,
                ),
            )
            if entry_types is not None:
                stmt = stmt.where(col(CreditLedgerEntry.entry_type).in_(entry_types))
            if cursor is not None:
                stmt = stmt.where(
                    or_(
                        col(CreditLedgerEntry.created_at) < cursor.created_at,
                        and_(
                            col(CreditLedgerEntry.created_at) == cursor.created_at,
                            col(CreditLedgerEntry.id) < cursor.id,
                        ),
                    )
                )
            stmt = stmt.order_by(
                col(CreditLedgerEntry.created_at).desc(),
                col(CreditLedgerEntry.id).desc(),
            ).limit(limit + 1)
            return list(session.exec(stmt).all())

    async def set_receipt_url(self, session_id: str, url: str) -> None:
        with session_scope(self._database_url) as session:
            row = session.exec(
                select(CreditLedgerEntry).where(CreditLedgerEntry.session_id == session_id)
            ).first()
            if row is not None:
                row.receipt_url = url
                session.add(row)

    async def has_purchase(self, user_id: UserId, session_id: str) -> bool:
        with session_scope(self._database_url) as session:
            return (
                session.exec(
                    select(CreditLedgerEntry.id).where(
                        CreditLedgerEntry.user_id == str(user_id),
                        CreditLedgerEntry.session_id == session_id,
                        CreditLedgerEntry.entry_type == "purchase",
                    )
                ).first()
                is not None
            )

    async def record_event(
        self,
        event_type: str,
        *,
        user_id: str | None = None,
        anon_id: str | None = None,
        source: str = "server",
        session_id: str | None = None,
        dedup_key: str | None = None,
        props: dict[str, object] | None = None,
    ) -> None:
        """Open a session and append one analytics event (standalone path)."""
        with session_scope(self._database_url) as session:
            record_event(
                session,
                event_type,
                user_id=user_id,
                anon_id=anon_id,
                source=source,
                session_id=session_id,
                dedup_key=dedup_key,
                props=props,
            )

    async def record_checkout_started(self, user_id: UserId, pack: str) -> None:
        # Intent, not outcome — may legitimately repeat, so no dedup key.
        await self.record_event(
            "checkout_started",
            user_id=str(user_id),
            props={"pack": pack},
        )
