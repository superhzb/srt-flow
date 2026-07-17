"""Product-analytics event ingestion, catalog, and retention.

One generic ``event`` table, two ingestion paths that share this module:
server emitters call :func:`record_event` inside their own transaction;
client events arrive via ``POST /api/events`` and route through the same
function. Every event type MUST have a catalog entry — the props
whitelist is enforced on every write, regardless of source.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from .models import Event

__all__ = [
    "CLIENT_ALLOWED_EVENTS",
    "DEFAULT_RETENTION_DAYS",
    "EVENT_CATALOG",
    "EventSpec",
    "anonymize_old_events",
    "record_event",
    "validate_props",
]

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 365


@dataclass(frozen=True, slots=True)
class EventSpec:
    """Catalog contract for one event type."""

    source: str  # 'server' | 'client' — the side allowed to originate it
    allowed_props: frozenset[str]  # props whitelist; unknown keys are rejected


# The single source of truth. An event type absent here cannot be written.
EVENT_CATALOG: dict[str, EventSpec] = {
    "user_signed_up": EventSpec("server", frozenset({"provider"})),
    "user_logged_in": EventSpec("server", frozenset({"provider"})),
    "job_created": EventSpec("server", frozenset({"job_id", "src_lang", "tgt_langs"})),
    "job_completed": EventSpec("server", frozenset({"job_id", "source_minutes"})),
    "job_failed": EventSpec("server", frozenset({"job_id", "error_kind"})),
    "checkout_started": EventSpec("server", frozenset({"pack"})),
    "purchase_completed": EventSpec("server", frozenset({"pack", "ledger_entry_id"})),
    "credits_debited": EventSpec(
        "server",
        frozenset({"reason", "amount", "balance_after", "job_id", "ledger_entry_id"}),
    ),
    "screen_viewed": EventSpec("client", frozenset({"screen"})),
    "demo_started": EventSpec("client", frozenset()),
    "cta_clicked": EventSpec("client", frozenset({"cta"})),
}

# Types the client is allowed to POST. Anything else from /api/events → 400.
CLIENT_ALLOWED_EVENTS: frozenset[str] = frozenset(
    name for name, spec in EVENT_CATALOG.items() if spec.source == "client"
)

# Prop keys that identify a person and must be dropped at the retention
# horizon. The current catalog carries none, but the machinery is here so
# a future PII-bearing prop is anonymized without a code change elsewhere.
IDENTIFYING_PROPS: frozenset[str] = frozenset()


def validate_props(event_type: str, props: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``props`` after enforcing the per-event whitelist.

    Raises ``ValueError`` for an unknown event type or any prop key not on
    that type's whitelist. Keeps the fact append-only and PII-free.
    """
    spec = EVENT_CATALOG.get(event_type)
    if spec is None:
        raise ValueError(f"unknown event_type: {event_type!r}")
    unknown = set(props) - spec.allowed_props
    if unknown:
        raise ValueError(f"props not whitelisted for {event_type}: {sorted(unknown)}")
    return dict(props)


def record_event(
    session: Session,
    event_type: str,
    *,
    user_id: str | None = None,
    anon_id: str | None = None,
    source: str = "server",
    session_id: str | None = None,
    dedup_key: str | None = None,
    props: dict[str, Any] | None = None,
) -> Event | None:
    """Insert one event, honoring at-most-once semantics for keyed events.

    Validates type + props against :data:`EVENT_CATALOG`. Returns the new
    row, or ``None`` when a duplicate ``dedup_key`` means nothing was
    written. Safe inside a caller's open transaction: the insert runs in a
    nested savepoint so a duplicate rolls back only itself, never the
    surrounding unit of work.
    """
    clean_props = validate_props(event_type, props or {})
    if dedup_key is not None:
        existing = session.exec(select(Event.id).where(Event.dedup_key == dedup_key)).first()
        if existing is not None:
            return None
    event = Event(
        id=uuid.uuid4().hex,
        event_type=event_type,
        user_id=user_id,
        anon_id=anon_id,
        source=source,
        session_id=session_id,
        dedup_key=dedup_key,
        props=clean_props,
    )
    try:
        with session.begin_nested():
            session.add(event)
            session.flush()
    except IntegrityError:
        # Concurrent insert won the dedup race — at-most-once still holds.
        return None
    return event


def anonymize_old_events(
    session: Session,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> int:
    """Null identity fields on events older than the retention horizon.

    Nulls ``user_id`` / ``anon_id`` and strips any identifying props, while
    leaving ``event_type``, ``created_at``, and aggregate props intact — the
    row's fact is unchanged, only who-did-it is forgotten. Returns the count
    of rows anonymized.
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
    stmt = select(Event).where(
        col(Event.created_at) < cutoff,
        or_(col(Event.user_id).is_not(None), col(Event.anon_id).is_not(None)),
    )
    count = 0
    for row in session.exec(stmt).all():
        row.user_id = None
        row.anon_id = None
        if IDENTIFYING_PROPS:
            row.props = {k: v for k, v in row.props.items() if k not in IDENTIFYING_PROPS}
        session.add(row)
        count += 1
    return count
