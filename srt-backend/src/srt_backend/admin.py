"""Read-only SQLAdmin registration and authentication."""

from __future__ import annotations

from fastapi import FastAPI
from pkg_auth.api import (
    AuthSettings,
    get_user_store,
    is_admin,
    load_settings,
    resolve_user,
)
from pkg_job_orch.api import Event, Job, User, get_engine
from sqladmin import Admin, BaseView, ModelView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response

__all__ = ["register_admin"]


class AdminAuthentication(AuthenticationBackend):
    """Authorize SQLAdmin with the app's existing Google/JWT session."""

    async def login(self, request: Request) -> Response:
        del request
        return RedirectResponse("/api/auth/google/login", status_code=302)

    async def logout(self, request: Request) -> Response:
        request.session.clear()
        settings = load_settings()
        response = RedirectResponse("/", status_code=302)
        response.delete_cookie(settings.session_cookie_name)
        return response

    async def authenticate(self, request: Request) -> Response | bool:
        settings = load_settings()
        user = await resolve_user(request, settings, get_user_store())
        if user is None:
            return RedirectResponse("/api/auth/google/login", status_code=302)
        if not is_admin(user, settings):
            return PlainTextResponse("Forbidden", status_code=403)
        return True


class OAuthAdmin(Admin):
    """Redirect SQLAdmin's login route directly into the app OAuth flow."""

    async def login(self, request: Request) -> Response:
        backend = self.authentication_backend
        if backend is None:
            return PlainTextResponse("Authentication backend unavailable", status_code=503)
        response = await backend.login(request)
        if isinstance(response, Response):
            return response
        return RedirectResponse("/api/auth/google/login", status_code=302)


class UserAdmin(ModelView, model=User):
    name = "User"
    name_plural = "Users"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    can_import = False
    column_list = ["id", "email", "tier", "google_sub", "created_at"]
    column_details_list = ["id", "email", "tier", "google_sub", "created_at"]


class JobAdmin(ModelView, model=Job):
    name = "Job"
    name_plural = "Jobs"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    can_import = False
    column_list = [
        "id",
        "filename",
        "user_id",
        "status",
        "worker",
        "src_lang",
        "tgt_langs",
        "progress",
        "created_at",
    ]
    column_details_list = [
        "id",
        "filename",
        "user_id",
        "status",
        "worker",
        "src_lang",
        "tgt_langs",
        "progress",
        "created_at",
        "started_at",
        "finished_at",
        "error_kind",
        "attempts",
    ]


class EventAdmin(ModelView, model=Event):
    name = "Event"
    name_plural = "Events"
    can_create = False
    can_edit = False
    can_delete = False
    can_export = False
    can_import = False
    column_default_sort = ("created_at", True)
    column_list = ["created_at", "event_type", "source", "user_id", "anon_id", "props"]
    column_details_list = [
        "id",
        "created_at",
        "event_type",
        "source",
        "user_id",
        "anon_id",
        "session_id",
        "dedup_key",
        "props",
    ]
    column_searchable_list = ["event_type", "user_id", "anon_id"]


def _render_table(title: str, headers: list[str], rows: list[tuple[object, ...]]) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = (
        "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
        or f"<tr><td colspan='{len(headers)}'>(no data)</td></tr>"
    )
    return (
        "<div class='col-12'>"
        "<div class='card'>"
        f"<div class='card-header'><h3 class='card-title'>{title}</h3></div>"
        "<div class='table-responsive'>"
        "<table class='table table-vcenter card-table'>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody>"
        "</table>"
        "</div></div></div>"
    )


class AnalyticsView(BaseView):
    name = "Analytics"

    @expose("/analytics", methods=["GET"])
    async def analytics(self, request: Request) -> Response:
        with get_engine().connect() as conn:

            def q(sql: str) -> list[tuple[object, ...]]:
                return [tuple(row) for row in conn.execute(text(sql)).all()]

            by_type = q(
                "SELECT event_type, COUNT(*) FROM event GROUP BY event_type ORDER BY COUNT(*) DESC"
            )
            dau = q(
                "SELECT date(created_at) d, COUNT(DISTINCT user_id) "
                "FROM event WHERE user_id IS NOT NULL "
                "GROUP BY d ORDER BY d DESC LIMIT 14"
            )
            jobs_day = q(
                "SELECT date(created_at) d, COUNT(*) FROM event "
                "WHERE event_type='job_created' GROUP BY d ORDER BY d DESC LIMIT 14"
            )
            funnel = q(
                "SELECT event_type, COUNT(*) FROM event "
                "WHERE event_type IN ('job_created','job_completed','job_failed') "
                "GROUP BY event_type"
            )
            signups = conn.execute(
                text("SELECT COUNT(DISTINCT user_id) FROM event WHERE event_type='user_signed_up'")
            ).scalar_one()
            buyers = conn.execute(
                text(
                    "SELECT COUNT(DISTINCT user_id) FROM event "
                    "WHERE event_type='purchase_completed'"
                )
            ).scalar_one()

        rate = f"{(buyers / signups * 100):.1f}%" if signups else "—"

        def static(path: str) -> str:
            return str(request.url_for("admin:statics", path=path))

        css = "".join(
            f"<link rel='stylesheet' href='{static(p)}'>"
            for p in (
                "css/tabler.min.css",
                "css/tabler-icons.min.css",
                "css/fontawesome-all.min.css",
                "css/main.css",
            )
        )
        body = (
            "<div class='page-wrapper'><div class='container-fluid'>"
            "<div class='page-header d-print-none'>"
            "<div class='row align-items-center'><div class='col'>"
            "<h2 class='page-title'>Analytics</h2>"
            "<div class='page-pretitle'>Product metrics</div>"
            "</div></div></div>"
            "<div class='page-body'><div class='container-fluid'>"
            "<div class='row row-deck row-cards'>"
            "<div class='col-12'>"
            "<a href='/admin/' class='btn btn-secondary btn-icon mb-3'>"
            "<i class='fa fa-arrow-left me-2'></i>Back to admin</a>"
            "</div>"
            + _render_table(
                "Sign-up \u2192 purchase conversion",
                ["signups", "buyers", "conversion"],
                [(signups, buyers, rate)],
            )
            + _render_table("Events by type", ["event_type", "count"], by_type)
            + _render_table("Daily active users (14d)", ["day", "users"], dau)
            + _render_table("Jobs created / day (14d)", ["day", "jobs"], jobs_day)
            + _render_table("Job funnel", ["stage", "count"], funnel)
            + "</div></div></div></div></div>"
        )
        html = (
            "<!DOCTYPE html><html lang='en'><head>"
            "<meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1, "
            "viewport-fit=cover'>"
            f"{css}"
            f"<title>Analytics \u00b7 srt-flow admin</title>"
            f"</head><body class='theme-dark'>{body}</body></html>"
        )
        return HTMLResponse(html)


async def _redirect_to_admin() -> Response:
    return RedirectResponse("/admin/", status_code=307)


def register_admin(app: FastAPI) -> Admin:
    """Mount the admin app before the frontend catch-all is registered."""
    settings = AuthSettings()
    secret = settings.admin_session_secret
    if secret is None:
        settings.validate_runtime()
        raise RuntimeError("ADMIN_SESSION_SECRET is required")

    app.add_api_route(
        "/admin",
        _redirect_to_admin,
        methods=["GET"],
        include_in_schema=False,
    )
    admin = OAuthAdmin(
        app,
        engine=get_engine(),
        title="srt-flow admin",
        authentication_backend=AdminAuthentication(secret.get_secret_value()),
    )
    admin.add_view(UserAdmin)
    admin.add_view(JobAdmin)
    admin.add_view(EventAdmin)
    admin.add_view(AnalyticsView)
    return admin
