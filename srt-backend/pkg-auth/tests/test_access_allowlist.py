from __future__ import annotations

import pytest
from pkg_auth.api import AuthSettings
from pkg_auth.dependencies import (  # pyright: ignore[reportPrivateUsage]
    _identity_allowed,
    is_admin,
    is_allowed,
)
from pkg_job_orch.api import User


def _user(*, sub: str, email: str) -> User:
    return User(id="uid", google_sub=sub, email=email, tier="free")


def test_allowlists_are_csv_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ALLOWED_SUBS", " 123, ABC ,123 ")
    monkeypatch.setenv("ALLOWED_EMAILS", " Tester@Example.COM ")

    settings = AuthSettings()

    assert settings.allowed_subs == frozenset({"123", "abc"})
    assert settings.allowed_emails == frozenset({"tester@example.com"})


def test_dev_is_always_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ALLOWED_EMAILS", "only@allowed.test")

    settings = AuthSettings()

    assert _identity_allowed("stranger-sub", "stranger@example.test", settings) is True


def test_empty_allowlist_is_open(monkeypatch: pytest.MonkeyPatch) -> None:
    # Production is a public product: no allowlist configured => open to all.
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.delenv("ALLOWED_SUBS", raising=False)
    monkeypatch.delenv("ALLOWED_EMAILS", raising=False)

    settings = AuthSettings()

    assert _identity_allowed("anyone", "anyone@example.test", settings) is True


def test_staging_allowlist_blocks_stranger_allows_listed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("ALLOWED_EMAILS", "superhzb@gmail.com")
    monkeypatch.delenv("ALLOWED_SUBS", raising=False)
    monkeypatch.delenv("ADMIN_SUBS", raising=False)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    settings = AuthSettings()

    # Case-insensitive match on the listed email.
    assert _identity_allowed("any-sub", "SuperHZB@Gmail.com", settings) is True
    assert is_allowed(_user(sub="any-sub", email="superhzb@gmail.com"), settings) is True
    # Everyone else is rejected.
    assert _identity_allowed("evil-sub", "attacker@example.test", settings) is False
    assert is_allowed(_user(sub="evil-sub", email="attacker@example.test"), settings) is False


def test_admins_always_pass_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("ALLOWED_EMAILS", "someone-else@example.test")
    monkeypatch.setenv("ADMIN_SUBS", "admin-sub")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)

    settings = AuthSettings()

    # Admin sub is not on ALLOWED_* yet still gets in.
    assert _identity_allowed("admin-sub", "admin@example.test", settings) is True


def test_admin_email_recognized_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("ADMIN_EMAILS", "superhzb@gmail.com")
    monkeypatch.delenv("ADMIN_SUBS", raising=False)

    settings = AuthSettings()

    assert is_admin(_user(sub="whatever", email="SuperHZB@gmail.com"), settings) is True
    assert is_admin(_user(sub="whatever", email="nobody@example.test"), settings) is False


def test_staging_allows_admin_emails_without_subs(monkeypatch: pytest.MonkeyPatch) -> None:
    # validate_runtime must accept ADMIN_EMAILS as a substitute for ADMIN_SUBS.
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("AUTH_MODE", "google")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-with-at-least-32-bytes")
    monkeypatch.setenv("ADMIN_SESSION_SECRET", "admin-session-secret")
    monkeypatch.setenv("ADMIN_EMAILS", "superhzb@gmail.com")
    monkeypatch.delenv("ADMIN_SUBS", raising=False)

    AuthSettings().validate_runtime()  # must not raise
