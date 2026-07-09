"""Session JWT tests — expiry, tampering, missing subject (PLAN: "expired → 401").

These were previously untested: ``verify_session_token`` is the auth gate but
had no direct coverage of its failure modes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from pkg_auth.config import AuthSettings
from pkg_auth.models import User
from pkg_auth.tokens import mint_session_token, verify_session_token
from pydantic import SecretStr


def _settings() -> AuthSettings:
    # model_construct (alias-free, validator-free) sidesteps pyright's lack of
    # modeling for pydantic-settings alias init kwargs.
    return AuthSettings.model_construct(
        jwt_secret=SecretStr("test-secret-test-secret-test-secret-0123456789"),
    )


def _user() -> User:
    return User(id="u-1", google_sub="sub-abc", email="user@example.test", tier="free")


def test_mint_then_verify_round_trips_subject() -> None:
    settings = _settings()
    token = mint_session_token(_user(), settings)

    assert verify_session_token(token, settings) == "sub-abc"


def test_expired_token_is_rejected_with_401() -> None:
    settings = _settings()
    now = datetime.now(UTC)
    expired = pyjwt.encode(
        {
            "sub": "sub-abc",
            "email": "user@example.test",
            "tier": "free",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        settings.jwt_secret.get_secret_value() if settings.jwt_secret else "",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        verify_session_token(expired, settings)
    assert exc.value.status_code == 401


def test_tampered_signature_is_rejected_with_401() -> None:
    settings = _settings()
    # Same payload, different secret → signature won't verify.
    tampered = pyjwt.encode(
        {
            "sub": "sub-abc",
            "email": "user@example.test",
            "tier": "free",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        "a-different-secret",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        verify_session_token(tampered, settings)
    assert exc.value.status_code == 401


def test_token_missing_subject_is_rejected_with_401() -> None:
    settings = _settings()
    token = pyjwt.encode(
        {"email": "user@example.test", "tier": "free"},
        settings.jwt_secret.get_secret_value() if settings.jwt_secret else "",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        verify_session_token(token, settings)
    assert exc.value.status_code == 401


def test_mint_without_configured_secret_raises_500() -> None:
    settings = AuthSettings.model_construct(jwt_secret=None)
    with pytest.raises(HTTPException) as exc:
        mint_session_token(_user(), settings)
    assert exc.value.status_code == 500
