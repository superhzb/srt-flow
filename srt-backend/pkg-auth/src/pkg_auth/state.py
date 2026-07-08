"""Runtime state hooks for auth dependencies."""

from __future__ import annotations

from pkg_auth.models import InMemoryUserStore, UserStore

_user_store: UserStore = InMemoryUserStore()


def get_user_store() -> UserStore:
    return _user_store


def set_user_store(user_store: UserStore) -> None:
    global _user_store
    _user_store = user_store
