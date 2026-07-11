"""FastAPI application factory + lifespan.

Slice 3 wires durable job orchestration: the lifespan runs Alembic,
seeds the dev user, replays pending/processing jobs onto the queue, and
starts the single ``worker_loop``. The job routes live in
``pkg_job_orch.routes`` and read shared state off ``app.state.job_ctx``.

The production Vite build is served at the root after the API routes. Hashed
assets are immutable; the HTML shell is always revalidated so deployments
cannot mix asset versions.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from pkg_auth.api import set_user_store
from pkg_billing.api import set_billing_store
from pkg_file_upload.api import LocalStorage
from pkg_job_orch.api import (
    DEV_USER_ID,
    JobContext,
    NullNotifier,
    enqueue_pending,
    get_engine,
    recover_jobs,
    reset_engine,
    run_migrations,
    seed_dev_user,
    worker_loop,
)
from sqlmodel import Session
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from srt_backend.app_store import AppStore
from srt_backend.routes_health import router as health_router
from srt_backend.routes_srt import router as srt_router
from srt_backend.routes_workers import router as workers_router

__all__ = ["api"]

logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class SpaStaticFiles(StaticFiles):
    """Serve a Vite SPA with safe cache headers and history fallback."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.startswith("assets/"):
                raise
            response = await super().get_response("index.html", scope)

        request_path = str(scope.get("path", ""))
        if request_path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response


def _build_ctx() -> JobContext:
    return JobContext(
        queue=asyncio.Queue(),
        storage=LocalStorage(os.environ.get("STORAGE_ROOT", "./.data/dev/storage")),
        dev_user_id=DEV_USER_ID,
        notifier=NullNotifier(),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """App startup/shutdown — see PLAN.md slice 3, "Worker lifecycle".

    startup:
      1. ``alembic upgrade head`` against ``DATABASE_URL``.
      2. Seed the dev user (idempotent) — slice 4 swaps to OAuth upsert.
      3. Recover-scan: reset ``processing`` → ``pending``; re-enqueue
         every ``pending`` row (volatile queue + durable rows = both).
      4. Start ``worker_loop``.

    shutdown:
      Stop the loop cleanly; the in-flight job is left ``processing`` and
      resumes next boot via the recover-scan.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())

    ctx = _build_ctx()
    app.state.job_ctx = ctx
    app.state.worker_stop = asyncio.Event()
    database_url = os.environ.get("DATABASE_URL")
    app_store = AppStore(database_url)
    app.state.app_store = app_store
    set_user_store(app_store)
    set_billing_store(app_store)

    run_migrations(database_url)

    with Session(get_engine(database_url)) as session:
        seed_dev_user(session)
        reset = recover_jobs(session)
        replayed = enqueue_pending(ctx, session)
        session.commit()
    if reset or replayed:
        logger.info("lifespan startup: recovered %d, replayed %d", reset, replayed)

    worker_task = asyncio.create_task(worker_loop(ctx, app.state.worker_stop))
    app.state.worker_task = worker_task

    try:
        yield
    finally:
        app.state.worker_stop.set()
        try:
            await asyncio.wait_for(worker_task, timeout=5.0)
        except TimeoutError:
            logger.warning("worker_loop did not shut down within 5s; cancelling")
            worker_task.cancel()
        # Drop the engine cache so a next run/test starts fresh.
        reset_engine()
        # Also clear the cached ctx so the next lifespan rebuilds it
        # (matters for tests that re-enter the lifespan).
        try:
            del app.state.job_ctx
        except AttributeError:
            pass


def _create_app() -> FastAPI:
    from pkg_auth.api import router as auth_router
    from pkg_billing.api import router as billing_router
    from pkg_job_orch.api import db_router
    from pkg_job_orch.api import router as jobs_router

    app = FastAPI(title="srt-flow", version="0.1.0", lifespan=lifespan)
    app.include_router(auth_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(billing_router, prefix="/api")
    app.include_router(srt_router, prefix="/api")
    app.include_router(workers_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(db_router, prefix="/api")

    frontend_dist = Path(__file__).resolve().parents[3] / "srt-frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/", SpaStaticFiles(directory=frontend_dist, html=True), name="frontend")
    else:
        logger.warning("frontend build not found at %s; static SPA is disabled", frontend_dist)
    return app


api = _create_app()
