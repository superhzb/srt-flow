"""Google OAuth helpers and routes."""

from __future__ import annotations

import secrets
from typing import Annotated, Any, cast
from urllib.parse import urlencode

import httpx
from authlib.jose import JsonWebKey, jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from pkg_auth.config import AuthSettings, load_settings
from pkg_auth.models import UserStore
from pkg_auth.state import get_user_store
from pkg_auth.tokens import mint_session_token

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"]

router = APIRouter(prefix="/google", tags=["auth"])


@router.get("/login")
async def login(settings: Annotated[AuthSettings, Depends(load_settings)]) -> Response:
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    response.set_cookie(
        settings.csrf_cookie_name,
        state,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/callback")
async def callback(
    request: Request,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    settings: Annotated[AuthSettings, Depends(load_settings)],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> Response:
    expected_state = request.cookies.get(settings.csrf_cookie_name)
    if expected_state is None or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")

    tokens = await exchange_code_for_tokens(settings, code)
    id_token = tokens.get("id_token")
    if not isinstance(id_token, str):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing id_token")

    claims = await verify_id_token(settings, id_token)
    subject = claims.get("sub")
    email = claims.get("email")
    email_verified = claims.get("email_verified")
    if not isinstance(subject, str) or not isinstance(email, str) or email_verified is not True:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid id_token claims",
        )

    user = await user_store.upsert(google_sub=subject, email=email, tier="free")
    session = mint_session_token(user, settings)
    response = RedirectResponse(settings.app_redirect_path)
    response.set_cookie(
        settings.session_cookie_name,
        session,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.jwt_ttl_hours * 3600,
    )
    response.delete_cookie(settings.csrf_cookie_name)
    return response


async def exchange_code_for_tokens(settings: AuthSettings, code: str) -> dict[str, Any]:
    if settings.google_client_secret is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google client secret is not configured",
        )
    data = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret.get_secret_value(),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": settings.google_redirect_uri,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data=data)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth token exchange failed",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth response",
        )
    return cast(dict[str, Any], payload)


async def verify_id_token(settings: AuthSettings, id_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(GOOGLE_JWKS_URL)
    if response.status_code >= 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google key fetch failed",
        )

    key_set = JsonWebKey.import_key_set(response.json())
    try:
        claims = cast(
            Any,
            jwt.decode(  # pyright: ignore[reportUnknownMemberType]
                id_token,
                key_set,
                claims_options={
                    "iss": {"values": GOOGLE_ISSUERS},
                    "aud": {"values": [settings.google_client_id]},
                    "exp": {"essential": True},
                },
            ),
        )
        claims.validate()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid id_token",
        ) from exc

    return cast(dict[str, Any], dict(claims))
