from __future__ import annotations

import pytest
from pkg_auth.api import AuthSettings


def test_admin_allowlists_are_csv_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ADMIN_SUBS", " 123, ABC,123 ")
    monkeypatch.setenv("ADMIN_EMAILS", " Admin@Example.COM, ops@example.com ")

    settings = AuthSettings()

    assert settings.admin_subs == frozenset({"123", "abc"})
    assert settings.admin_emails == frozenset({"admin@example.com", "ops@example.com"})


def test_dev_admin_secret_has_fixed_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.delenv("ADMIN_SESSION_SECRET", raising=False)

    settings = AuthSettings()
    settings.validate_runtime()

    assert settings.admin_session_secret is not None


@pytest.mark.parametrize("missing", ["ADMIN_SESSION_SECRET", "ADMIN_SUBS"])
def test_prod_requires_admin_config(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("AUTH_MODE", "google")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-with-at-least-32-bytes")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "admin-session-secret")
    monkeypatch.setenv("ADMIN_SUBS", "admin-sub")
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError, match=missing):
        AuthSettings().validate_runtime()
