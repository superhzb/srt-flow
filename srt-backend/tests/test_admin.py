from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pkg_job_orch.api import Event, Job, User, get_engine, reset_engine
from sqlmodel import Session


def _set_google_env(monkeypatch: pytest.MonkeyPatch) -> str:
    jwt_secret = "test-jwt-secret-with-at-least-32-bytes"
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "google")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("JWT_SECRET", jwt_secret)
    monkeypatch.setenv("ADMIN_SUBS", " ADMIN-SUB ")
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("ADMIN_SESSION_SECRET", raising=False)
    return jwt_secret


def _frontend_dist(path: Path) -> Path:
    path.mkdir()
    (path / "index.html").write_text("<h1>SPA SHELL MARKER</h1>")
    return path


def _create_test_app(frontend_dist: Path) -> FastAPI:
    from srt_backend.app import _create_app  # pyright: ignore[reportPrivateUsage]

    reset_engine()
    return _create_app(frontend_dist=frontend_dist)


def _token(subject: str, secret: str, *, expired: bool = False) -> str:
    expires = datetime.now(UTC) + (timedelta(hours=-1) if expired else timedelta(hours=1))
    return jwt.encode({"sub": subject, "exp": expires}, secret, algorithm="HS256")


def _add_admin_data(database_url: str) -> tuple[str, str]:
    user = User(
        id="admin-user-id",
        google_sub="Admin-Sub",
        email="admin@example.test",
        tier="paid",
    )
    job = Job(
        id="admin-job-id",
        filename="admin.srt",
        user_id=user.id,
        worker="cloud",
        src_lang="en",
        tgt_langs="fr",
        error="TOP SECRET ERROR BODY",
        progress_by_target="TOP SECRET PROGRESS BODY",
        dropped_by_target="TOP SECRET DROPPED BODY",
    )
    now = datetime.now(UTC)
    specs = [
        ("screen_viewed", {"anon_id": "anon-1"}),
        ("screen_viewed", {"anon_id": "anon-2"}),
        ("demo_started", {"anon_id": "anon-1"}),
        ("cta_clicked", {"anon_id": "anon-1"}),
        ("user_signed_up", {"user_id": user.id}),
        ("purchase_completed", {"user_id": user.id}),
        ("job_created", {"user_id": user.id}),
        ("job_completed", {"user_id": user.id}),
    ]
    events = [
        Event(id=f"admin-event-{i}", event_type=et, created_at=now, **kw)
        for i, (et, kw) in enumerate(specs)
    ]
    with Session(get_engine(database_url)) as session:
        session.add(user)
        session.add(job)
        for event in events:
            session.add(event)
        session.commit()
    return "admin-user-id", "admin-job-id"


def test_admin_access_matrix_and_read_only_views(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
    tmp_path: Path,
) -> None:
    secret = _set_google_env(monkeypatch)
    app = _create_test_app(_frontend_dist(tmp_path / "dist"))

    with TestClient(app, follow_redirects=False) as client:
        anonymous = client.get("/admin/")
        assert anonymous.status_code == 302
        assert anonymous.headers["location"] == "/api/auth/google/login"

        client.cookies.set("srt_session", "malformed")
        malformed = client.get("/admin/")
        assert malformed.status_code == 302
        assert malformed.headers["location"] == "/api/auth/google/login"

        client.cookies.set("srt_session", _token("admin-sub", secret, expired=True))
        expired = client.get("/admin/")
        assert expired.status_code == 302
        assert expired.headers["location"] == "/api/auth/google/login"

        user_id, job_id = _add_admin_data(temp_env["DATABASE_URL"])
        client.cookies.set("srt_session", _token("ordinary-sub", secret))
        ordinary = client.get("/admin/")
        assert ordinary.status_code == 302
        assert ordinary.headers["location"] == "/api/auth/google/login"

        with Session(get_engine(temp_env["DATABASE_URL"])) as session:
            session.add(
                User(
                    id="ordinary-user-id",
                    google_sub="ordinary-sub",
                    email="ordinary@example.test",
                )
            )
            session.commit()
        ordinary = client.get("/admin/")
        assert ordinary.status_code == 403

        client.cookies.set("srt_session", _token("Admin-Sub", secret))
        index = client.get("/admin/")
        assert index.status_code == 200
        assert "Users" in index.text
        assert "Jobs" in index.text
        assert "SPA SHELL MARKER" not in index.text

        assert client.get("/admin/user/list").status_code == 200
        assert client.get("/admin/job/list").status_code == 200

        detail = client.get(f"/admin/job/details/{job_id}")
        assert detail.status_code == 200
        assert "admin.srt" in detail.text
        assert "TOP SECRET ERROR BODY" not in detail.text
        assert "TOP SECRET PROGRESS BODY" not in detail.text
        assert "TOP SECRET DROPPED BODY" not in detail.text

        assert client.get("/admin/user/create").status_code == 403
        assert client.get(f"/admin/user/edit/{user_id}").status_code == 403
        assert client.delete(f"/admin/user/delete?pks={user_id}").status_code == 403
        assert client.get("/admin/user/export/csv").status_code == 403
        assert client.post("/admin/user/import").status_code == 403

        logout = client.get("/admin/logout")
        assert logout.status_code == 302
        assert logout.headers["location"] == "/"
        assert 'srt_session=""' in logout.headers["set-cookie"]

        client.cookies.set("srt_session", _token("Admin-Sub", secret))
        analytics = client.get("/admin/analytics")
        assert analytics.status_code == 200
        assert "<!DOCTYPE html>" in analytics.text
        assert "/admin/statics/css/tabler.min.css" in analytics.text
        assert "class='page-wrapper'" in analytics.text
        assert "class='table table-vcenter card-table'" in analytics.text
        assert "Sign-up" in analytics.text and "Job funnel" in analytics.text
        assert "Acquisition funnel" in analytics.text
        assert "Demo started" in analytics.text and "CTA clicked" in analytics.text
        # Redesigned UI: KPI hero cards, funnel drop-off bars, sparklines.
        assert "class='subheader'>Visitors" in analytics.text
        assert "conversion rate" in analytics.text
        assert "progress-bar" in analytics.text
        assert "<polyline" in analytics.text
        assert "class='analytics-title'>Analytics" in analytics.text
        assert "class='analytics-kicker'>Product metrics" in analytics.text
        assert "class='container-fluid analytics-shell'" in analytics.text
        assert analytics.text.index("Analytics</h1>") < analytics.text.index("Product metrics")
        assert "aria-label='Back to admin dashboard'" in analytics.text
        assert "<div class='page-body'><div class='container-fluid'>" not in analytics.text

    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any(path.startswith("/api/db") for path in paths)


def test_dev_admin_works_without_jwt_or_custom_admin_secret(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
    tmp_path: Path,
) -> None:
    del temp_env
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "DEV@LOCAL")
    monkeypatch.setenv("ADMIN_EMAILS", " dev@local ")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_SESSION_SECRET", raising=False)
    app = _create_test_app(_frontend_dist(tmp_path / "dist"))

    with TestClient(app, follow_redirects=False) as client:
        assert client.get("/admin").headers["location"] == "/admin/"
        response = client.get("/admin/")

    assert response.status_code == 200
    assert "Users" in response.text
    assert "SPA SHELL MARKER" not in response.text


def test_admin_login_redirects_to_google(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
    tmp_path: Path,
) -> None:
    del temp_env
    _set_google_env(monkeypatch)
    app = _create_test_app(_frontend_dist(tmp_path / "dist"))

    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/admin/login")

    assert response.status_code == 302
    assert response.headers["location"] == "/api/auth/google/login"
