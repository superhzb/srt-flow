"""Billing store protocol and process singleton.

The in-memory ``InMemoryBillingStore`` that used to live here was deleted
in Phase 3 #9 — the DB-backed ``AppStore`` is the sole store
implementation. ``get_billing_store`` has no default; the app lifespan
wires the real store via :func:`set_billing_store` at composition root.
Unit tests inject their own fakes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pkg_auth.api import User

__all__ = [
    "BillingStore",
    "LedgerCursor",
    "LedgerEntry",
    "UserId",
    "get_billing_store",
    "set_billing_store",
]

UserId = str | int


@dataclass(frozen=True)
class LedgerCursor:
    created_at: datetime
    id: str


class LedgerEntry(Protocol):
    id: str
    created_at: datetime
    entry_type: str
    minutes_delta: int
    usage_minutes: int
    balance_after: int | None
    pack: str | None
    amount_cents: int | None
    currency: str | None
    reason: str | None
    receipt_url: str | None


class BillingStore(Protocol):
    async def get_by_id(self, user_id: UserId) -> User | None: ...

    async def get_by_email(self, email: str) -> list[User]: ...

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
        """Record a paid session and credit its minutes exactly once."""
        ...

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
    ) -> bool: ...

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
    ) -> bool: ...

    async def list_ledger(
        self,
        user_id: UserId,
        limit: int,
        cursor: LedgerCursor | None = None,
        entry_types: frozenset[str] | None = None,
    ) -> Sequence[LedgerEntry]: ...

    async def set_receipt_url(self, session_id: str, url: str) -> None: ...

    async def has_purchase(self, user_id: UserId, session_id: str) -> bool: ...

    async def balance(self, user_id: UserId, free_limit: int) -> dict[str, int]: ...

    async def record_checkout_started(self, user_id: UserId, pack: str) -> None: ...


_billing_store: BillingStore | None = None


def set_billing_store(store: BillingStore) -> None:
    """Set the process-wide billing store dependency."""
    global _billing_store
    _billing_store = store


def get_billing_store() -> BillingStore:
    global _billing_store
    if _billing_store is None:
        msg = "billing store not configured; call set_billing_store at composition root"
        raise RuntimeError(msg)
    return _billing_store
