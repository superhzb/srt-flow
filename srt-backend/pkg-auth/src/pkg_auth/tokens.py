"""JWT session token helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from pkg_auth.config import AuthSettings
from pkg_auth.models import User


def mint_session_token(user: User, settings: AuthSettings) -> str:
    secret = _jwt_secret(settings)
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user.google_sub,
        "email": user.email,
        "tier": user.tier,
        "iat": now,
        "exp": now + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def verify_session_token(token: str, settings: AuthSettings) -> str:
    secret = _jwt_secret(settings)
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        ) from exc

    subject = payload.get("sub")
    if not isinstance(subject, str) or subject == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
        )
    return subject


def _jwt_secret(settings: AuthSettings) -> str:
    if settings.jwt_secret is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT secret is not configured",
        )
    return settings.jwt_secret.get_secret_value()
