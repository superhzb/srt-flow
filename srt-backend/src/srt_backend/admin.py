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
from pkg_job_orch.api import Job, User, get_engine
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response

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
    return admin
