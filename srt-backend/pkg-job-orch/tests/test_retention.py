"""Unit tests for data retention (purge_old_jobs) and erasure (erase_user)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pkg_file_upload.api import LocalStorage
from pkg_job_orch.api import (
    Event,
    Job,
    User,
    erase_user,
    purge_old_jobs,
    session_scope,
)


def _make_job(job_id: str, user_id: str, created_at: datetime) -> Job:
    return Job(
        id=job_id,
        user_id=user_id,
        worker="mlx",
        src_lang="en",
        tgt_langs="fr",
        created_at=created_at,
    )


def test_purge_removes_old_job_row_and_files(temp_db: str, temp_storage: LocalStorage) -> None:
    now = datetime.now(UTC)
    old = _make_job("old", "u1", now - timedelta(days=60))
    fresh = _make_job("fresh", "u1", now - timedelta(days=1))
    temp_storage.save("u1", "old", "input.srt", b"old")
    temp_storage.save("u1", "fresh", "input.srt", b"fresh")

    with session_scope(temp_db) as session:
        session.add(old)
        session.add(fresh)

    with session_scope(temp_db) as session:
        purged = purge_old_jobs(session, temp_storage, retention_days=30, now=now)

    assert purged == 1
    with session_scope(temp_db) as session:
        assert session.get(Job, "old") is None
        assert session.get(Job, "fresh") is not None
    # On-disk artifacts follow the row.
    assert not (temp_storage.root / "u1" / "old").exists()
    assert (temp_storage.root / "u1" / "fresh" / "input.srt").exists()


def test_purge_noop_when_nothing_old(temp_db: str, temp_storage: LocalStorage) -> None:
    now = datetime.now(UTC)
    with session_scope(temp_db) as session:
        session.add(_make_job("j", "u1", now - timedelta(days=1)))
    with session_scope(temp_db) as session:
        assert purge_old_jobs(session, temp_storage, retention_days=30, now=now) == 0


def test_erase_user_removes_identity_and_content(temp_db: str, temp_storage: LocalStorage) -> None:
    now = datetime.now(UTC)
    with session_scope(temp_db) as session:
        session.add(User(id="u1", email="a@example.com", google_sub="sub-1"))
        session.add(User(id="u2", email="b@example.com", google_sub="sub-2"))
        session.add(_make_job("j1", "u1", now))
        session.add(_make_job("j2", "u1", now))
        session.add(_make_job("other", "u2", now))
        session.add(Event(id="e1", event_type="demo_started", user_id="u1", anon_id="a1"))
        session.add(Event(id="e2", event_type="demo_started", user_id="u2", anon_id="a2"))
    temp_storage.save("u1", "j1", "input.srt", b"x")
    temp_storage.save("u2", "other", "input.srt", b"y")

    with session_scope(temp_db) as session:
        result = erase_user(session, temp_storage, "u1")

    assert result.user_deleted is True
    assert result.jobs_deleted == 2
    assert result.events_anonymized == 1

    with session_scope(temp_db) as session:
        assert session.get(User, "u1") is None
        assert session.get(User, "u2") is not None  # other user untouched
        assert session.get(Job, "j1") is None
        assert session.get(Job, "other") is not None
        e1 = session.get(Event, "e1")
        assert e1 is not None and e1.user_id is None and e1.anon_id is None
        e2 = session.get(Event, "e2")
        assert e2 is not None and e2.user_id == "u2"  # other user's identity kept

    assert not (temp_storage.root / "u1").exists()
    assert (temp_storage.root / "u2" / "other" / "input.srt").exists()


def test_erase_user_is_idempotent(temp_db: str, temp_storage: LocalStorage) -> None:
    with session_scope(temp_db) as session:
        first = erase_user(session, temp_storage, "ghost")
    assert first.user_deleted is False
    assert first.jobs_deleted == 0
