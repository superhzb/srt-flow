# authlib.jose is untyped, so the unknown-type family of strict checks is
# noisy across this file (google.py suppresses the same per-line). Scoped off
# here rather than littering per-line ignores.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

"""Google id_token JWKS verification tests (#27).

``verify_id_token`` fetches Google's JWKS and validates the id_token signature
+ iss/aud/exp. Previously untested (needs network). Driven via httpx
``MockTransport`` against an in-process generated RSA key — no real network.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import httpx
import pytest
from authlib.jose import JsonWebKey, KeySet
from authlib.jose import jwt as authlib_jwt
from fastapi import HTTPException
from pkg_auth import google
from pkg_auth.config import AuthSettings
from pkg_auth.google import GOOGLE_ISSUERS, GOOGLE_JWKS_URL, verify_id_token

CLIENT_ID = "test-client-id"


def _settings() -> AuthSettings:
    # model_construct sidesteps pyright's lack of pydantic-settings alias init.
    return AuthSettings.model_construct(google_client_id=CLIENT_ID)


def _patch_httpx(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    """Route google.py's httpx.AsyncClient through a MockTransport."""
    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def factory(*_args: object, **kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("timeout", None)
        kwargs["transport"] = transport
        return real_async_client(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(google.httpx, "AsyncClient", factory)


def _mint_id_token(key: object, *, aud: str, exp_delta: int = 3600) -> str:
    now = int(time.time())
    raw = authlib_jwt.encode(
        {"alg": "RS256"},
        {
            "iss": GOOGLE_ISSUERS[0],
            "aud": aud,
            "sub": "g-sub-1",
            "email": "user@example.test",
            "iat": now,
            "exp": now + exp_delta,
        },
        key,
    )
    return raw.decode("ascii")


def test_verify_id_token_returns_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    jwks = KeySet([key]).as_dict()
    id_token = _mint_id_token(key, aud=CLIENT_ID)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=jwks)

    _patch_httpx(monkeypatch, handler)

    claims = asyncio.run(verify_id_token(_settings(), id_token))
    assert claims["sub"] == "g-sub-1"
    assert claims["email"] == "user@example.test"


def test_verify_id_token_key_fetch_failure_is_400(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    _patch_httpx(monkeypatch, handler)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(verify_id_token(_settings(), "header.payload.sig"))
    assert exc.value.status_code == 400
    assert exc.value.detail == "Google key fetch failed"


def test_verify_id_token_wrong_audience_is_400(monkeypatch: pytest.MonkeyPatch) -> None:
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    jwks = KeySet([key]).as_dict()
    id_token = _mint_id_token(key, aud="some-other-client")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == GOOGLE_JWKS_URL
        return httpx.Response(200, json=jwks)

    _patch_httpx(monkeypatch, handler)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(verify_id_token(_settings(), id_token))
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid id_token"


def test_verify_id_token_expired_is_400(monkeypatch: pytest.MonkeyPatch) -> None:
    key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    jwks = KeySet([key]).as_dict()
    id_token = _mint_id_token(key, aud=CLIENT_ID, exp_delta=-3600)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=jwks)

    _patch_httpx(monkeypatch, handler)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(verify_id_token(_settings(), id_token))
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid id_token"
