"""Integration tests for pkg-auth mounted in the mono-app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_auth_routes_reset_legacy_paid_user_to_free(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env

    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "dev@example.test")
    monkeypatch.setenv("DEV_USER_TIER", "paid")
    monkeypatch.setenv("ADMIN_EMAILS", "dev@example.test")

    from srt_backend.app import api

    with TestClient(api) as client:
        me = client.get("/api/auth/me")
        paid = client.get("/api/auth/paid-check")

    assert me.status_code == 200
    assert me.json()["id"] == "dev-user"
    assert me.json()["email"] == "dev@example.test"
    assert me.json()["tier"] == "free"
    assert me.json()["is_admin"] is True
    assert isinstance(me.json()["created_at"], str)
    assert paid.status_code == 402
    assert paid.json() == {"detail": "Upgrade required"}
