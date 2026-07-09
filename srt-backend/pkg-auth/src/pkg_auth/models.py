"""Auth store interface.

The canonical ``User`` row lives in ``pkg_job_orch`` because job orchestration
owns the app database. It is re-imported here so the auth ``UserStore``
protocol has a concrete type without duplicating the model. The in-memory
``User`` dataclass + ``InMemoryUserStore`` that used to live here were deleted;
the DB-backed ``AppStore`` is the sole store implementation.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pkg_job_orch.api import User

__all__ = ["Tier", "User", "UserStore"]

Tier = Literal["free", "paid"]


class UserStore(Protocol):
    async def get_by_sub(self, google_sub: str) -> User | None: ...

    async def upsert(self, *, google_sub: str, email: str, tier: Tier = "free") -> User: ...

    async def get_dev_user(self, *, email: str, tier: Tier) -> User: ...
