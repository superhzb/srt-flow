"""SQLModel tables for srt-flow.

Two tables land in slice 3: ``user`` (one seeded dev row) and ``job``.
``google_sub`` arrives in slice 4 via Alembic migration — the slice-3
schema intentionally omits it.

One job = one upload → N targets. ``tgt_langs`` is CSV (the target list
is small and stable; CSV is one less moving part than JSON over a TEXT
column). Output paths are *derived* (``{job_id}/output.<lang>.srt``),
never stored — the row carries no path columns.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

__all__ = [
    "Job",
    "JobStatus",
    "ProcessedEvent",
    "User",
    "dropped_from_json",
    "dropped_to_json",
    "tgt_langs_to_csv",
    "tgt_langs_from_csv",
]

JobStatus = str  # Literal["pending", "processing", "done", "failed"] — free str for SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


def tgt_langs_to_csv(langs: list[str]) -> str:
    """Serialise the target-language list to a CSV column value.

    Order preserved; empty list → empty string. Whitespace inside codes
    is not tolerated (worker codes never contain it).
    """
    return ",".join(langs)


def tgt_langs_from_csv(value: str | None) -> list[str]:
    """Inverse of :func:`tgt_langs_to_csv`. Empty/None → empty list."""
    if not value:
        return []
    return [c for c in value.split(",") if c]


def dropped_to_json(dropped: dict[str, int]) -> str:
    """Serialise per-target dropped-cue counts to stable JSON text."""
    return json.dumps(dropped, separators=(",", ":"), sort_keys=True)


def dropped_from_json(value: str | None) -> dict[str, int]:
    """Parse per-target dropped-cue counts. Empty/None becomes an empty dict."""
    if not value:
        return {}
    parsed = json.loads(value)
    return {str(target): int(count) for target, count in parsed.items()}


class User(SQLModel, table=True):
    """Canonical durable user row shared by auth, billing, and job orchestration."""

    id: str = Field(primary_key=True)
    email: str
    tier: str = Field(default="free")
    google_sub: str | None = Field(default=None, unique=True)
    created_at: datetime = Field(default_factory=_utcnow)


class ProcessedEvent(SQLModel, table=True):
    """Stripe webhook event idempotency ledger."""

    __tablename__: Any = "processed_events"

    event_id: str = Field(primary_key=True)
    session_id: str
    user_id: str = Field(foreign_key="user.id", index=True)
    paid_at: str
    created_at: datetime = Field(default_factory=_utcnow)


class Job(SQLModel, table=True):
    """One translation job: one input → N target outputs."""

    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    status: JobStatus = Field(default="pending", index=True)
    worker: str
    src_lang: str
    tgt_langs: str = Field(default="")  # CSV — see tgt_langs_from_csv
    progress: float = Field(default=0.0)
    error: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow)
    started_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    finished_at: datetime | None = Field(default=None)
    error_kind: str | None = Field(default=None)
    dropped_by_target: str | None = Field(default=None)
    attempts: int = Field(default=0)

    def model_dump_summary(self) -> dict[str, Any]:
        """Compact dict for the GET /api/jobs list response."""
        return {
            "id": self.id,
            "status": self.status,
            "worker": self.worker,
            "src_lang": self.src_lang,
            "tgt_langs": tgt_langs_from_csv(self.tgt_langs),
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "error_kind": self.error_kind,
            "attempts": self.attempts,
        }
