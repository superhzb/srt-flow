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


def _card(title: str, inner: str, *, span: str = "col-12", subtitle: str = "") -> str:
    sub = f"<div class='card-subtitle'>{subtitle}</div>" if subtitle else ""
    return (
        f"<div class='{span}'><div class='card'>"
        f"<div class='card-header'><div><h3 class='card-title'>{title}</h3>{sub}</div></div>"
        f"<div class='card-body'>{inner}</div>"
        "</div></div>"
    )


def _render_kpis(cards: list[tuple[str, object, str, str]]) -> str:
    """Hero stat row. Each card: (label, value, color_class, sublabel)."""
    cols = []
    for label, value, color, sub in cards:
        cols.append(
            "<div class='col-sm-6 col-lg-3'>"
            "<div class='card card-sm'><div class='card-body'>"
            f"<div class='subheader'>{label}</div>"
            f"<div class='h1 mb-0 mt-1 {color}'>{value}</div>"
            f"<div class='text-secondary small'>{sub}</div>"
            "</div></div></div>"
        )
    return "".join(cols)


def _render_funnel(
    title: str,
    stages: list[tuple[str, int]],
    colors: list[str],
    *,
    subtitle: str = "",
) -> str:
    """Stacked drop-off bars. Bar width = % of first stage; delta = step-to-step."""
    top = stages[0][1] if stages else 0
    prev: int | None = None
    rows = []
    for i, (label, count) in enumerate(stages):
        color = colors[i % len(colors)]
        width = (count / top * 100) if top else 0
        pct = f"{width:.0f}% of top" if top else "—"
        drop = ""
        if prev is not None:
            if prev > 0:
                delta = (count / prev - 1) * 100
                cls = "text-red" if delta < 0 else "text-green"
                drop = f"<span class='{cls} small ms-2'>{delta:+.0f}%</span>"
            else:
                drop = "<span class='text-secondary small ms-2'>—</span>"
        rows.append(
            "<div class='mb-3'>"
            "<div class='d-flex align-items-baseline mb-1'>"
            f"<div class='text-secondary'>{label}</div>"
            "<div class='ms-auto'>"
            f"<strong class='h3 mb-0'>{count}</strong>"
            f"<span class='text-secondary small ms-2'>{pct}</span>{drop}"
            "</div></div>"
            "<div class='progress' style='height:.75rem'>"
            f"<div class='progress-bar' role='progressbar' "
            f"style='width:{width:.1f}%;background-color:{color}'></div>"
            "</div></div>"
        )
    return _card(title, "".join(rows), subtitle=subtitle)


def _sparkline_svg(values: list[float], color: str) -> str:
    """Inline area sparkline. No JS, no external chart lib."""
    if not values:
        return "<div class='text-secondary'>(no data)</div>"
    w, h, pad = 320.0, 56.0, 3.0
    n = len(values)
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0

    def px(i: int) -> float:
        return (i / (n - 1)) * w if n > 1 else w / 2

    def py(v: float) -> float:
        return h - pad - ((v - lo) / span) * (h - 2 * pad)

    line = " ".join(f"{px(i):.1f},{py(v):.1f}" for i, v in enumerate(values))
    area = (
        f"M0,{h:.0f} "
        + " ".join(f"L{px(i):.1f},{py(v):.1f}" for i, v in enumerate(values))
        + f" L{w:.0f},{h:.0f} Z"
    )
    return (
        f"<svg viewBox='0 0 {w:.0f} {h:.0f}' preserveAspectRatio='none' "
        "style='width:100%;height:56px' xmlns='http://www.w3.org/2000/svg'>"
        f"<path d='{area}' fill='{color}' fill-opacity='0.15'/>"
        f"<polyline points='{line}' fill='none' stroke='{color}' "
        "stroke-width='2' stroke-linejoin='round' stroke-linecap='round'/>"
        "</svg>"
    )


def _render_sparkline(
    title: str, series_desc: list[tuple[object, int]], color: str, unit: str
) -> str:
    """series_desc: (day, value) newest-first (as queried). Renders latest + trend."""
    asc = list(reversed(series_desc))
    values = [float(v) for _, v in asc]
    latest = int(values[-1]) if values else 0
    total = int(sum(values))
    inner = (
        "<div class='d-flex align-items-baseline mb-2'>"
        f"<span class='h1 mb-0 me-2'>{latest}</span>"
        f"<span class='text-secondary'>{unit} latest · {total} total (14d)</span>"
        "</div>" + _sparkline_svg(values, color)
    )
    return _card(title, inner, span="col-lg-6")


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
            funnel_rows = q(
                "SELECT event_type, COUNT(*) FROM event "
                "WHERE event_type IN ('job_created','job_completed','job_failed') "
                "GROUP BY event_type"
            )
            funnel_counts = {str(t): int(c) for t, c in funnel_rows}

            # Acquisition funnel: the top-of-funnel visitor journey market
            # testing cares about. Stages 1-3 count distinct anon_id (the
            # pre-login browser id); stages 4-5 count distinct user_id. The two
            # denominators differ, so the % column is an approximate drop-off,
            # not an exact per-visitor rate — enough to read where traffic dies.
            def _distinct(col: str, where: str) -> int:
                return conn.execute(
                    text(f"SELECT COUNT(DISTINCT {col}) FROM event WHERE {where}")
                ).scalar_one()

            visitors = _distinct("anon_id", "event_type='screen_viewed' AND anon_id IS NOT NULL")
            demo = _distinct("anon_id", "event_type='demo_started' AND anon_id IS NOT NULL")
            cta = _distinct("anon_id", "event_type='cta_clicked' AND anon_id IS NOT NULL")
            signed = _distinct("user_id", "event_type='user_signed_up'")
            bought = _distinct("user_id", "event_type='purchase_completed'")

            acq_stages = [
                ("1. Visitors (screen viewed)", visitors),
                ("2. Demo started", demo),
                ("3. CTA clicked", cta),
                ("4. Signed up", signed),
                ("5. Purchased", bought),
            ]
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
        analytics_css = (
            "<style>"
            ".analytics-shell{width:100%;max-width:1180px;margin:0 auto}"
            ".analytics-header{padding:2rem 0 1.25rem;border-bottom:1px solid "
            "rgba(98,105,118,.18)}"
            ".analytics-heading{display:flex;align-items:center;gap:1rem}"
            ".analytics-heading-icon{display:grid;place-items:center;width:3rem;height:3rem;"
            "border-radius:.75rem;background:rgba(66,99,235,.14);color:#748ffc;"
            "font-size:1.25rem;box-shadow:inset 0 0 0 1px rgba(116,143,252,.18)}"
            ".analytics-title{margin:0;font-size:2rem;font-weight:700;letter-spacing:-.025em;"
            "line-height:1.1}"
            ".analytics-kicker{margin-top:.35rem;color:var(--tblr-secondary-color);"
            "font-size:.875rem;font-weight:500}"
            ".admin-return{border-color:rgba(98,105,118,.45);background:rgba(255,255,255,.02);"
            "transition:background-color .15s ease,border-color .15s ease,color .15s ease,"
            "box-shadow .15s ease,transform .15s ease}"
            ".admin-return:hover{color:#fff;border-color:#748ffc;background:rgba(66,99,235,.24);"
            "box-shadow:0 0 0 3px rgba(116,143,252,.14);transform:translateY(-1px)}"
            ".admin-return:focus-visible{color:#fff;border-color:#748ffc;"
            "box-shadow:0 0 0 3px rgba(116,143,252,.28)}"
            "@media(max-width:575.98px){.analytics-header{padding-top:1.25rem}"
            ".analytics-heading-icon{width:2.5rem;height:2.5rem}"
            ".analytics-title{font-size:1.75rem}.admin-return-label{display:none}"
            ".admin-return .fa{margin-right:0!important}}"
            "</style>"
        )
        conv_color = "text-green" if signups and (buyers / signups) >= 0.05 else "text-red"
        kpis = _render_kpis(
            [
                ("Visitors", visitors, "", "distinct browsers"),
                ("Signed up", signups, "", "distinct accounts"),
                ("Buyers", buyers, "", "distinct purchasers"),
                ("Sign-up \u2192 purchase", rate, conv_color, "conversion rate"),
            ]
        )

        acq_colors = ["#4263eb", "#4dabf7", "#22b8cf", "#20c997", "#51cf66"]
        job_created = funnel_counts.get("job_created", 0)
        job_stages = [
            ("Created", job_created),
            ("Completed", funnel_counts.get("job_completed", 0)),
            ("Failed", funnel_counts.get("job_failed", 0)),
        ]

        def _section(title: str) -> str:
            return (
                "<div class='col-12'>"
                f"<h3 class='mt-2 mb-0 text-uppercase text-secondary'>{title}</h3>"
                "<hr class='mt-2'/></div>"
            )

        body = (
            "<div class='page-wrapper'><div class='container-fluid analytics-shell'>"
            "<header class='page-header d-print-none analytics-header'>"
            "<div class='row align-items-center g-3'><div class='col'>"
            "<div class='analytics-heading'>"
            "<div class='analytics-heading-icon' aria-hidden='true'>"
            "<i class='fa fa-chart-line'></i></div>"
            "<div><h1 class='analytics-title'>Analytics</h1>"
            "<div class='analytics-kicker'>Product metrics</div></div>"
            "</div></div><div class='col-auto'>"
            "<a href='/admin/' class='btn btn-outline-secondary admin-return' "
            "aria-label='Back to admin dashboard'>"
            "<i class='fa fa-arrow-left me-2' aria-hidden='true'></i>"
            "<span class='admin-return-label'>Admin dashboard</span></a>"
            "</div></div></header>"
            "<main class='page-body'>"
            "<div class='row row-deck row-cards'>"
            + kpis
            + _section("Acquisition")
            + _render_funnel(
                "Acquisition funnel",
                acq_stages,
                acq_colors,
                subtitle="stages 1-3 count browsers, 4-5 count accounts \u2014 "
                "% is approximate drop-off",
            )
            + _section("Product health")
            + _render_funnel(
                "Job funnel",
                job_stages,
                ["#748ffc", "#51cf66", "#ff6b6b"],
            )
            + _render_table("Events by type", ["event_type", "count"], by_type)
            + _section("Trends")
            + _render_sparkline("Daily active users (14d)", dau, "#4dabf7", "users")
            + _render_sparkline("Jobs created / day (14d)", jobs_day, "#20c997", "jobs")
            + "</div></main></div></div>"
        )
        html = (
            "<!DOCTYPE html><html lang='en'><head>"
            "<meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1, "
            "viewport-fit=cover'>"
            f"{css}{analytics_css}"
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
