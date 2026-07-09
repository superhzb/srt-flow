"""Shared prototype app store for auth and billing.

This is a dev-only bridge until the auth user model is unified with the
durable job-orch user table.
"""

from __future__ import annotations

from pkg_auth.api import User, UserStore
from pkg_auth.models import Tier
from pkg_billing.api import BillingStore

__all__ = ["AppStore"]


class AppStore(UserStore, BillingStore):
    """In-memory store shared by pkg-auth and pkg-billing in one process."""

    def __init__(self) -> None:
        self._next_id = 1
        self._users_by_id: dict[int, User] = {}
        self._users_by_sub: dict[str, User] = {}
        self._processed_events: set[str] = set()
        self._usage_this_period: dict[int, int] = {}

    async def get_by_sub(self, google_sub: str) -> User | None:
        return self._users_by_sub.get(google_sub)

    async def upsert(self, *, google_sub: str, email: str, tier: Tier = "free") -> User:
        existing = self._users_by_sub.get(google_sub)
        if existing is None:
            user = User(id=self._next_id, google_sub=google_sub, email=email, tier=tier)
            self._next_id += 1
        else:
            next_tier: Tier = "paid" if existing.tier == "paid" and tier == "free" else tier
            user = User(id=existing.id, google_sub=google_sub, email=email, tier=next_tier)

        self._store_user(user)
        return user

    async def get_dev_user(self, *, email: str, tier: Tier) -> User:
        return await self.upsert(google_sub=f"dev:{email}", email=email, tier=tier)

    async def get_by_id(self, user_id: int) -> User | None:
        return self._users_by_id.get(user_id)

    async def get_by_email(self, email: str) -> list[User]:
        return [user for user in self._users_by_id.values() if user.email == email]

    async def mark_paid(
        self,
        user_id: int,
        *,
        event_id: str,
        session_id: str,
        paid_at: str,
    ) -> None:
        del event_id, session_id, paid_at
        user = self._users_by_id[user_id]
        self._store_user(
            User(
                id=user.id,
                google_sub=user.google_sub,
                email=user.email,
                tier="paid",
            )
        )

    async def has_processed_event(self, event_id: str) -> bool:
        return event_id in self._processed_events

    async def record_event(self, event_id: str) -> None:
        self._processed_events.add(event_id)

    async def usage_count_this_period(self, user_id: int) -> int:
        return self._usage_this_period.get(user_id, 0)

    def _store_user(self, user: User) -> None:
        self._users_by_id[user.id] = user
        self._users_by_sub[user.google_sub] = user
