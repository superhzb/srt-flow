from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pkg_job_orch.api import (
    DEV_USER_ID,
    Job,
    db_router,
    init_schema,
    reset_engine,
    seed_dev_user,
    session_scope,
    tgt_langs_to_csv,
)


@pytest.fixture
def route_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    db_url = f"sqlite:///{tmp_path / 'route.sqlite'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    reset_engine()
    init_schema(db_url)
    yield db_url
    reset_engine()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(db_router, prefix="/api")
    return TestClient(app)


def _seed_jobs(count: int) -> None:
    with session_scope() as session:
        seed_dev_user(session)
        for i in range(count):
            session.add(
                Job(
                    id=f"job-{i:02d}",
                    user_id=DEV_USER_ID,
                    status="pending",
                    worker="mlx",
                    src_lang="en",
                    tgt_langs=tgt_langs_to_csv(["fr"]),
                    progress=0.0,
                )
            )


def test_list_tables_returns_counts(route_db: str) -> None:
    _seed_jobs(2)
    client = _client()

    resp = client.get("/api/db/tables")

    assert resp.status_code == 200
    assert resp.json() == [{"name": "user", "count": 1}, {"name": "job", "count": 2}]


def test_table_rows_are_paged_and_bounds_checked(route_db: str) -> None:
    _seed_jobs(25)
    client = _client()

    page = client.get("/api/db/tables/job?page=1&size=20")

    assert page.status_code == 200
    body: dict[str, Any] = page.json()
    assert body["columns"] == [
        "id",
        "filename",
        "user_id",
        "status",
        "worker",
        "src_lang",
        "tgt_langs",
        "progress",
        "error",
        "created_at",
        "started_at",
        "finished_at",
        "error_kind",
        "dropped_by_target",
        "attempts",
    ]
    assert body["total"] == 25
    assert body["page"] == 1
    assert body["size"] == 20
    assert [row["id"] for row in body["rows"]] == [f"job-{i:02d}" for i in range(20, 25)]

    assert client.get("/api/db/tables/job?page=-1").status_code == 422
    assert client.get("/api/db/tables/job?size=0").status_code == 422
    assert client.get("/api/db/tables/nope").status_code == 404


def test_clear_empties_tables_and_reseeds_dev_user(route_db: str) -> None:
    _seed_jobs(3)
    client = _client()

    resp = client.post("/api/db/clear")

    assert resp.status_code == 200
    assert resp.json() == {"cleared": 4}
    assert client.get("/api/db/tables").json() == [
        {"name": "user", "count": 1},
        {"name": "job", "count": 0},
    ]
    users = client.get("/api/db/tables/user").json()
    assert users["rows"][0]["id"] == DEV_USER_ID
