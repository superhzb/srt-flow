"""Public API for pkg_auth."""

from pkg_auth.config import AuthSettings, load_settings
from pkg_auth.dependencies import (
    get_current_user,
    is_admin,
    require_admin,
    require_tier,
    resolve_user,
)
from pkg_auth.models import User, UserStore
from pkg_auth.router import router
from pkg_auth.state import get_user_store, set_user_store

__all__ = [
    "User",
    "UserStore",
    "AuthSettings",
    "get_current_user",
    "get_user_store",
    "is_admin",
    "load_settings",
    "require_admin",
    "require_tier",
    "resolve_user",
    "router",
    "set_user_store",
]
