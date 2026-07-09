"""Tests for /api/workers and /api/languages routes (Phase 6 #28).

The routes are a thin layer over pkg_job_orch worker helpers; they were
previously untested. probe_workers/fetch_languages are monkeypatched so no
real worker HTTP is made.
"""

from __future__ import annotations

from typing import Any

import pytest
import srt_backend.routes_workers as routes_workers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pkg_job_orch.workers import WorkerStatus


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(routes_workers.router, prefix="/api")
    return app


@pytest.fixture
def workers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKERS", "cloud=http://up:5733,mlx=http://down:5732")


def test_list_workers_reports_health_per_worker(
    workers_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del workers_env

    async def fake_probe(infos: Any) -> list[WorkerStatus]:
        return [
            WorkerStatus(id=i.id, label=i.label, healthy=(i.id == "cloud"))
            for i in infos
        ]

    monkeypatch.setattr(routes_workers, "probe_workers", fake_probe)

    with TestClient(_app()) as client:
        resp = client.get("/api/workers")

    assert resp.status_code == 200
    body = resp.json()
    assert body["workers"] == [
        {"id": "cloud", "label": "Cloud (DeepSeek)", "healthy": True},
        {"id": "mlx", "label": "Local MLX", "healthy": False},
    ]


def test_list_languages_returns_worker_json(
    workers_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del workers_env
    payload: dict[str, object] = {"languages": [{"code": "es", "name": "Spanish"}]}

    async def fake_fetch(_base_url: str) -> dict[str, object]:
        return payload

    monkeypatch.setattr(routes_workers, "fetch_languages", fake_fetch)

    with TestClient(_app()) as client:
        resp = client.get("/api/languages?worker=mlx")

    assert resp.status_code == 200
    assert resp.json() == payload


def test_list_languages_unknown_worker_is_404(workers_env: None) -> None:
    del workers_env

    with TestClient(_app()) as client:
        resp = client.get("/api/languages?worker=nope")

    assert resp.status_code == 404
    assert "unknown worker" in resp.json()["detail"]


def test_list_languages_worker_failure_is_502(
    workers_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del workers_env

    async def exploding(_base_url: str) -> dict[str, object]:
        raise RuntimeError("upstream down")

    monkeypatch.setattr(routes_workers, "fetch_languages", exploding)

    with TestClient(_app()) as client:
        resp = client.get("/api/languages?worker=mlx")

    assert resp.status_code == 502
    assert "worker languages call failed" in resp.json()["detail"]
