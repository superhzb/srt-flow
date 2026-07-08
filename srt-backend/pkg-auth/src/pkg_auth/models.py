"""Auth models and store interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

Tier = Literal["free", "paid"]


@dataclass(frozen=True, slots=True)
class User:
    id: int
    google_sub: str
    email: str
    tier: Tier


class UserStore(Protocol):
    async def get_by_sub(self, google_sub: str) -> User | None: ...

    async def upsert(self, *, google_sub: str, email: str, tier: Tier = "free") -> User: ...

    async def get_dev_user(self, *, email: str, tier: Tier) -> User: ...


class InMemoryUserStore:
    """Prototype user store until the mono-app grows a SQLite implementation."""

    def __init__(self) -> None:
        self._next_id = 1
        self._by_sub: dict[str, User] = {}

    async def get_by_sub(self, google_sub: str) -> User | None:
        return self._by_sub.get(google_sub)

    async def upsert(self, *, google_sub: str, email: str, tier: Tier = "free") -> User:
        existing = self._by_sub.get(google_sub)
        if existing is not None:
            user = User(id=existing.id, google_sub=google_sub, email=email, tier=tier)
        else:
            user = User(id=self._next_id, google_sub=google_sub, email=email, tier=tier)
            self._next_id += 1
        self._by_sub[google_sub] = user
        return user

    async def get_dev_user(self, *, email: str, tier: Tier) -> User:
        return await self.upsert(google_sub=f"dev:{email}", email=email, tier=tier)
