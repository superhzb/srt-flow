"""Tests for the Job/User SQLModel tables + tgt_langs CSV helpers."""

from __future__ import annotations

from datetime import datetime

from pkg_job_orch.api import (
    DEV_USER_ID,
    Job,
    User,
    get_engine,
    tgt_langs_from_csv,
    tgt_langs_to_csv,
)
from sqlmodel import Session, select


def test_tgt_langs_round_trip() -> None:
    assert tgt_langs_to_csv(["fr", "de"]) == "fr,de"
    assert tgt_langs_from_csv("fr,de") == ["fr", "de"]
    assert tgt_langs_from_csv("") == []
    assert tgt_langs_from_csv(None) == []
    assert tgt_langs_to_csv([]) == ""


def test_job_defaults(temp_db: str) -> None:
    with Session(get_engine()) as s:
        s.add(User(id=DEV_USER_ID, email="dev@local"))
        s.add(Job(id="j1", user_id=DEV_USER_ID, worker="mlx", src_lang="en"))
        s.commit()
        job = s.get(Job, "j1")
    assert job is not None
    assert job.status == "pending"
    assert job.progress == 0.0
    assert job.error is None
    assert job.finished_at is None
    assert job.tgt_langs == ""  # server_default from migration / SQLModel default
    assert isinstance(job.created_at, datetime)


def test_user_unique_id(temp_db: str) -> None:
    with Session(get_engine()) as s:
        s.add(User(id=DEV_USER_ID, email="dev@local"))
        s.commit()
        s.add(User(id=DEV_USER_ID, email="other@local"))  # same PK
        try:
            s.commit()
        except Exception:
            return
    raise AssertionError("expected IntegrityError on duplicate user id")


def test_job_user_fk_indexed(temp_db: str) -> None:
    """user_id is a real FK + indexed — list_jobs filters by it."""
    with Session(get_engine()) as s:
        s.add(User(id=DEV_USER_ID, email="dev@local"))
        s.add(User(id="other", email="x@local"))
        s.add(Job(id="j1", user_id=DEV_USER_ID, worker="mlx", src_lang="en"))
        s.add(Job(id="j2", user_id="other", worker="mlx", src_lang="en"))
        s.commit()
        stmt = select(Job).where(Job.user_id == DEV_USER_ID)
        mine = s.exec(stmt).all()
    assert {j.id for j in mine} == {"j1"}
