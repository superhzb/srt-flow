# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnusedFunction=false

import importlib
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pkg_auth.api import __all__ as public_names
from pkg_auth.api import router
from pkg_auth.models import Tier, User


class _FakeUserStore:
    """In-process UserStore for unit tests (no DB). Mirrors the sticky-paid
    upsert semantics of the real AppStore so tier behaviour is exercised."""

    def __init__(self) -> None:
        self._by_sub: dict[str, User] = {}

    async def get_by_sub(self, google_sub: str) -> User | None:
        return self._by_sub.get(google_sub)

    async def upsert(self, *, google_sub: str, email: str, tier: Tier = "free") -> User:
        existing = self._by_sub.get(google_sub)
        if existing is not None:
            existing.email = email
            existing.tier = "paid" if existing.tier == "paid" and tier == "free" else tier
            return existing
        user = User(id=uuid.uuid4().hex, google_sub=google_sub, email=email, tier=tier)
        self._by_sub[google_sub] = user
        return user

    async def get_dev_user(self, *, email: str, tier: Tier) -> User:
        return await self.upsert(google_sub=f"dev:{email}", email=email, tier=tier)


def test_public_api_all_names_are_resolvable() -> None:
    mod = importlib.import_module("pkg_auth.api")
    for name in public_names:
        assert hasattr(mod, name), f"{name} in __all__ but not defined in api"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return app


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reset the shared user store per test: dev-mode endpoints upsert the dev
    # user into the module-global store, and sticky-paid (#9) would otherwise
    # leak a paid tier from a prior test into this one.
    from pkg_auth.state import set_user_store

    set_user_store(_FakeUserStore())

    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "google")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://testserver/api/auth/google/callback")
    monkeypatch.setenv("JWT_SECRET", "test-secret-with-at-least-32-bytes")


def test_me_google_mode_without_cookie_401() -> None:
    with TestClient(_app()) as client:
        resp = client.get("/api/auth/me")

    assert resp.status_code == 401


def test_me_dev_mode_returns_seeded_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "dev@example.test")
    monkeypatch.setenv("DEV_USER_TIER", "paid")
    monkeypatch.setenv("ADMIN_EMAILS", "dev@example.test")

    with TestClient(_app()) as client:
        resp = client.get("/api/auth/me")

    assert resp.status_code == 200
    assert isinstance(resp.json()["id"], str)
    assert resp.json()["id"]
    assert resp.json()["email"] == "dev@example.test"
    assert resp.json()["tier"] == "paid"
    assert resp.json()["is_admin"] is True
    assert isinstance(resp.json()["created_at"], str)


def test_paid_check_allows_paid_dev_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_TIER", "paid")

    with TestClient(_app()) as client:
        resp = client.get("/api/auth/paid-check")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_paid_check_rejects_free_dev_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_TIER", "free")

    with TestClient(_app()) as client:
        resp = client.get("/api/auth/paid-check")

    assert resp.status_code == 402
    assert resp.json()["detail"] == "Upgrade required"


def test_prod_rejects_dev_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("AUTH_MODE", "dev")

    with pytest.raises(RuntimeError, match="AUTH_MODE must be 'google'"):
        with TestClient(_app()):
            pass


def test_google_login_sets_csrf_cookie() -> None:
    with TestClient(_app(), follow_redirects=False) as client:
        resp = client.get("/api/auth/google/login")

    assert resp.status_code == 307
    assert "accounts.google.com" in resp.headers["location"]
    assert "srt_oauth_state=" in resp.headers["set-cookie"]


def test_google_callback_rejects_bad_state() -> None:
    with TestClient(_app()) as client:
        resp = client.get("/api/auth/google/callback?code=abc&state=bad")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid OAuth state"


def test_google_callback_sets_session_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    google = importlib.import_module("pkg_auth.google")

    async def exchange_code_for_tokens(*_args: object, **_kwargs: object) -> dict[str, str]:
        return {"id_token": "id-token"}

    async def verify_id_token(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "sub": "google-sub",
            "email": "user@example.test",
            "email_verified": True,
        }

    monkeypatch.setattr(google, "exchange_code_for_tokens", exchange_code_for_tokens)
    monkeypatch.setattr(google, "verify_id_token", verify_id_token)

    with TestClient(_app(), follow_redirects=False) as client:
        client.get("/api/auth/google/login")
        state = client.cookies["srt_oauth_state"]
        resp = client.get(f"/api/auth/google/callback?code=abc&state={state}")

    assert resp.status_code == 307
    assert "srt_session=" in resp.headers["set-cookie"]


def test_google_callback_rejects_unverified_email(monkeypatch: pytest.MonkeyPatch) -> None:
    google = importlib.import_module("pkg_auth.google")

    async def exchange_code_for_tokens(*_args: object, **_kwargs: object) -> dict[str, str]:
        return {"id_token": "id-token"}

    async def verify_id_token(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "sub": "google-sub",
            "email": "user@example.test",
            "email_verified": False,
        }

    monkeypatch.setattr(google, "exchange_code_for_tokens", exchange_code_for_tokens)
    monkeypatch.setattr(google, "verify_id_token", verify_id_token)

    with TestClient(_app()) as client:
        client.get("/api/auth/google/login")
        state = client.cookies["srt_oauth_state"]
        resp = client.get(f"/api/auth/google/callback?code=abc&state={state}")

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid id_token claims"
