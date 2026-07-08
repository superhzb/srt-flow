"""Auth routes."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from pkg_auth.config import load_settings
from pkg_auth.dependencies import get_current_user, require_tier
from pkg_auth.google import router as google_router
from pkg_auth.models import User


@asynccontextmanager
async def auth_lifespan(_app: object) -> AsyncGenerator[None]:
    load_settings()
    yield


router = APIRouter(prefix="/auth", tags=["auth"], lifespan=auth_lifespan)
router.include_router(google_router)


@router.get("/me")
async def me(user: Annotated[User, Depends(get_current_user)]) -> dict[str, str]:
    return {"email": user.email, "tier": user.tier}


@router.post("/logout")
async def logout() -> Response:
    settings = load_settings()
    response = Response(status_code=204)
    response.delete_cookie(settings.session_cookie_name)
    return response


@router.get("/paid-check")
async def paid_check(
    user: Annotated[User, Depends(require_tier("paid"))],
) -> dict[str, bool]:
    del user
    return {"ok": True}
