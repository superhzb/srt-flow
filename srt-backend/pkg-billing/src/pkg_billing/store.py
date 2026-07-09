"""Billing store protocol and process singleton.

The in-memory ``InMemoryBillingStore`` that used to live here was deleted
in Phase 3 #9 — the DB-backed ``AppStore`` is the sole store
implementation. ``get_billing_store`` has no default; the app lifespan
wires the real store via :func:`set_billing_store` at composition root.
Unit tests inject their own fakes.
"""

from __future__ import annotations

from typing import Protocol

from pkg_auth.api import User

__all__ = ["BillingStore", "UserId", "get_billing_store", "set_billing_store"]

UserId = str | int


class BillingStore(Protocol):
    async def get_by_id(self, user_id: UserId) -> User | None: ...

    async def get_by_email(self, email: str) -> list[User]: ...

    async def apply_paid_webhook_once(
        self,
        event_id: str,
        session_id: str,
        user_id: UserId,
        paid_at: str,
    ) -> bool:
        """Record a paid webhook and flip the user to paid, exactly once.

        Atomic: the processed-event insert and the tier flip commit in a
        single transaction. Returns ``True`` if applied, ``False`` if the
        ``event_id`` was already recorded (idempotent no-op).
        """
        ...

    async def has_processed_event(self, event_id: str) -> bool:
        """Read-only idempotency check (not the write path)."""
        ...

    async def usage_count_this_period(self, user_id: UserId) -> int: ...


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
