"""FastAPI application factory.

Mounts all pkg-* routers under `/api`. Slice 1 wired only the SRT parse
router; slice 2 adds workers, languages, translate, and prepare.

Static SPA serving is deferred to slice 6 (deploy) — slices 1–5 are
exercised through the Vite dev proxy and the API routes directly.
"""

from __future__ import annotations

from fastapi import FastAPI

from srt_backend.routes_srt import router as srt_router
from srt_backend.routes_translate import router as translate_router
from srt_backend.routes_workers import router as workers_router

__all__ = ["api"]


def _create_app() -> FastAPI:
    app = FastAPI(title="srt-flow", version="0.1.0")
    app.include_router(srt_router, prefix="/api")
    app.include_router(workers_router, prefix="/api")
    app.include_router(translate_router, prefix="/api")
    return app


api = _create_app()
