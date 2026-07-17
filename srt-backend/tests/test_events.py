"""Analytics event backbone: catalog, dedup, client ingestion, retention."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pkg_job_orch.api import (
    Event,
    anonymize_old_events,
    get_engine,
    record_event,
    reset_engine,
    run_migrations,
    session_scope,
)
from sqlmodel import Session, select


@pytest.fixture(autouse=True)
def _isolate_engine() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Drop the cached engine before and after each test.

    The unit tests here build an engine without booting the app lifespan
    (which normally resets it on shutdown), so without this a stale engine
    keyed to this module's temp DB would leak into later test files.
    """
    reset_engine()
    yield
    reset_engine()


def _app() -> FastAPI:
    from srt_backend.app import _create_app  # pyright: ignore[reportPrivateUsage]

    return _create_app(frontend_dist=None)


def test_client_batch_accepted_and_stored(temp_env: dict[str, str]) -> None:
    with TestClient(_app()) as client:
        resp = client.post(
            "/api/events",
            json={
                "events": [
                    {"event_type": "screen_viewed", "props": {"screen": "landing"}},
                    {"event_type": "demo_started"},
                ],
                "session_id": "sess-1",
                "anon_id": "anon-1",
            },
        )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 2}
    with Session(get_engine(temp_env["DATABASE_URL"])) as session:
        rows = session.exec(select(Event)).all()
    assert {r.event_type for r in rows} == {"screen_viewed", "demo_started"}
    assert all(r.source == "client" and r.anon_id == "anon-1" for r in rows)


@pytest.mark.parametrize(
    "body",
    [
        {"events": [{"event_type": "not_a_thing"}], "anon_id": "a"},
        {"events": [{"event_type": "job_created", "props": {"job_id": "x"}}]},
        {"events": [{"event_type": "cta_clicked", "props": {"evil": 1}}], "anon_id": "a"},
        {"events": [{"event_type": "demo_started"}] * 21, "anon_id": "a"},
        {"events": [], "anon_id": "a"},
    ],
)
def test_client_batch_rejections(temp_env: dict[str, str], body: dict[str, object]) -> None:
    del temp_env
    with TestClient(_app()) as client:
        resp = client.post("/api/events", json=body)
    assert resp.status_code == 400


def test_client_body_too_large(temp_env: dict[str, str]) -> None:
    del temp_env
    with TestClient(_app()) as client:
        resp = client.post(
            "/api/events",
            json={"events": [{"event_type": "demo_started"}], "anon_id": "x" * 20_000},
        )
    assert resp.status_code == 413


def test_client_rate_limit(temp_env: dict[str, str]) -> None:
    del temp_env
    with TestClient(_app()) as client:
        codes = [
            client.post(
                "/api/events",
                json={"events": [{"event_type": "demo_started"}], "session_id": "rl-key"},
            ).status_code
            for _ in range(61)
        ]
    assert codes.count(202) == 60
    assert codes[-1] == 429


def test_record_event_dedup_and_whitelist(temp_env: dict[str, str]) -> None:
    del temp_env
    run_migrations()
    with session_scope() as session:
        first = record_event(session, "job_completed", dedup_key="job1:completed", props={})
        dup = record_event(session, "job_completed", dedup_key="job1:completed", props={})
        assert first is not None
        assert dup is None
        with pytest.raises(ValueError, match="not whitelisted"):
            record_event(session, "job_created", props={"nope": 1})
    with Session(get_engine()) as session:
        assert len(session.exec(select(Event)).all()) == 1


def test_anonymize_old_events(temp_env: dict[str, str]) -> None:
    del temp_env
    run_migrations()
    with session_scope() as session:
        old = record_event(
            session, "screen_viewed", source="client", user_id="u1", anon_id="a1",
            props={"screen": "landing"},
        )
        assert old is not None
        old.created_at = datetime.now(UTC) - timedelta(days=400)
        session.add(old)
        record_event(
            session, "screen_viewed", source="client", user_id="u2", anon_id="a2",
            props={"screen": "jobs"},
        )
    with session_scope() as session:
        assert anonymize_old_events(session) == 1
    with Session(get_engine()) as session:
        rows = {r.props["screen"]: r for r in session.exec(select(Event)).all()}
    assert rows["landing"].user_id is None and rows["landing"].anon_id is None
    assert rows["jobs"].user_id == "u2"  # recent row untouched
