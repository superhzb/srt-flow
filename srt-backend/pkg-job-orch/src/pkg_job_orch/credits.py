"""Minute metering and atomic credit-ledger operations."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pkg_srt_services.api import Cue
from sqlmodel import Session, func, select

from .models import CreditLedgerEntry, Job, User


@dataclass(frozen=True, slots=True)
class BalanceSnapshot:
    free_limit: int
    free_used: int
    free_remaining: int
    purchased_minutes: int

    @property
    def available_minutes(self) -> int:
        return self.free_remaining + self.purchased_minutes


def source_minutes(cues: list[Cue]) -> int:
    """Return max source cue end time rounded up to a whole minute."""
    max_ms = max((_timestamp_ms(cue.end) for cue in cues), default=0)
    return max(1, math.ceil(max_ms / 60_000))


def usage_month(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m")


def balance_snapshot(
    session: Session,
    user_id: str,
    free_limit: int,
    *,
    month: str | None = None,
) -> BalanceSnapshot:
    user = session.get(User, user_id)
    if user is None:
        raise LookupError(f"user {user_id} not found")
    selected_month = month or usage_month(datetime.now(UTC))
    used = session.exec(
        select(func.coalesce(func.sum(CreditLedgerEntry.usage_minutes), 0)).where(
            CreditLedgerEntry.user_id == user_id,
            CreditLedgerEntry.usage_month == selected_month,
            CreditLedgerEntry.entry_type == "job_debit",
        )
    ).one()
    free_used = min(int(used), free_limit)
    return BalanceSnapshot(
        free_limit=free_limit,
        free_used=free_used,
        free_remaining=max(0, free_limit - int(used)),
        purchased_minutes=user.purchased_minutes,
    )


def debit_job_once(session: Session, job: Job, free_limit: int) -> bool:
    """Meter a successful job once, consuming monthly free minutes first."""
    existing = session.exec(
        select(CreditLedgerEntry).where(CreditLedgerEntry.job_id == job.id)
    ).first()
    if existing is not None:
        return False
    user = session.get(User, job.user_id)
    if user is None:
        raise LookupError(f"user {job.user_id} not found")
    month = usage_month(job.created_at)
    snapshot = balance_snapshot(session, job.user_id, free_limit, month=month)
    purchased_debit = max(0, job.source_minutes - snapshot.free_remaining)
    session.add(
        CreditLedgerEntry(
            id=uuid.uuid4().hex,
            user_id=job.user_id,
            entry_type="job_debit",
            minutes_delta=-purchased_debit,
            balance_after=user.purchased_minutes - purchased_debit,
            usage_minutes=job.source_minutes,
            usage_month=month,
            idempotency_key=f"job:{job.id}",
            job_id=job.id,
            reason="successful translation",
        )
    )
    user.purchased_minutes -= purchased_debit
    session.add(user)
    return True


def _timestamp_ms(value: str) -> int:
    try:
        hours, minutes, seconds_millis = value.replace(".", ",").split(":")
        seconds, millis = seconds_millis.split(",")
        return (
            int(hours) * 3_600_000
            + int(minutes) * 60_000
            + int(seconds) * 1_000
            + int(millis.ljust(3, "0")[:3])
        )
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"invalid SRT timestamp: {value!r}") from exc
