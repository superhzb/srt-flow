"""FastAPI dependencies exposed by pkg-auth."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from pkg_auth.config import AuthSettings, Tier, load_settings
from pkg_auth.models import User, UserStore
from pkg_auth.state import get_user_store
from pkg_auth.tokens import verify_session_token

_TIER_RANK: dict[str, int] = {"free": 0, "paid": 1}


async def get_current_user(
    request: Request,
    settings: Annotated[AuthSettings, Depends(load_settings)],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> User:
    user = await resolve_user(request, settings, user_store)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def resolve_user(
    request: Request,
    settings: AuthSettings,
    user_store: UserStore,
) -> User | None:
    """Resolve the app user for an HTTP request without enforcing authentication."""
    if settings.env == "dev" and settings.auth_mode == "dev":
        return await user_store.get_dev_user(
            email=settings.dev_user_email,
            tier=settings.dev_user_tier,
        )

    token = request.cookies.get(settings.session_cookie_name)
    if token is None:
        return None

    try:
        google_sub = verify_session_token(token, settings)
    except HTTPException:
        return None
    user = await user_store.get_by_sub(google_sub)
    return user


def is_admin(user: User, settings: AuthSettings) -> bool:
    """Return whether a user is allowlisted for the current environment."""
    google_sub = (user.google_sub or "").strip().casefold()
    if google_sub in settings.admin_subs:
        return True
    return settings.env == "dev" and user.email.strip().casefold() in settings.admin_emails


async def require_admin(
    request: Request,
    settings: Annotated[AuthSettings, Depends(load_settings)],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> User:
    user = await resolve_user(request, settings, user_store)
    if user is None or not is_admin(user, settings):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_tier(tier: Tier) -> Callable[[User], Awaitable[User]]:
    async def _require_tier(user: Annotated[User, Depends(get_current_user)]) -> User:
        if _TIER_RANK[user.tier] < _TIER_RANK[tier]:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Upgrade required",
            )
        return user

    return _require_tier
