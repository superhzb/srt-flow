"""Runtime state hooks for auth dependencies.

The store has no built-in default — the app lifespan wires the real
DB-backed ``AppStore`` via :func:`set_user_store` at composition root
(REFACTOR_PLAN.md Phase 3 #9: one store, DB-backed). Accessing the store
before it is wired raises loudly instead of silently falling back to a
shadow in-memory implementation.
"""

from __future__ import annotations

from pkg_auth.models import UserStore

_user_store: UserStore | None = None


def get_user_store() -> UserStore:
    global _user_store
    if _user_store is None:
        msg = "user store not configured; call set_user_store at composition root"
        raise RuntimeError(msg)
    return _user_store


def set_user_store(user_store: UserStore) -> None:
    global _user_store
    _user_store = user_store
