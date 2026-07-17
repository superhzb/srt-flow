"""Client-side analytics ingestion — ``POST /api/events``.

Explicit tracking only (the frontend never auto-instruments ``fetch``).
Guards: batch/body caps, client-catalog + props whitelist, a per-session
rate limit, and a server-set ``created_at``. Auth is optional — anonymous
callers are allowed so pre-login screen views still land, carrying only an
``anon_id`` for query-time identity join.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pkg_auth.api import get_user_store, load_settings, resolve_user
from pkg_job_orch.api import CLIENT_ALLOWED_EVENTS, record_event, session_scope
from pydantic import BaseModel, Field, ValidationError

__all__ = ["router"]

router = APIRouter(prefix="/events", tags=["analytics"])

MAX_BATCH = 20
MAX_BODY_BYTES = 16 * 1024
RATE_LIMIT_PER_MIN = 60
_RATE_WINDOW_S = 60.0

# key (session_id | anon_id | client host) -> recent hit timestamps.
_rate_hits: dict[str, deque[float]] = defaultdict(deque)


class ClientEvent(BaseModel):
    event_type: str
    props: dict[str, Any] = Field(default_factory=dict)


class EventsBatch(BaseModel):
    events: list[ClientEvent] = Field(min_length=1, max_length=MAX_BATCH)
    session_id: str | None = None
    anon_id: str | None = None


def _rate_key(batch: EventsBatch, request: Request) -> str:
    if batch.session_id:
        return f"s:{batch.session_id}"
    if batch.anon_id:
        return f"a:{batch.anon_id}"
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def _check_rate(key: str, now: float) -> bool:
    hits = _rate_hits[key]
    cutoff = now - _RATE_WINDOW_S
    while hits and hits[0] < cutoff:
        hits.popleft()
    if len(hits) >= RATE_LIMIT_PER_MIN:
        return False
    hits.append(now)
    return True


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(request: Request) -> dict[str, int]:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"body exceeds {MAX_BODY_BYTES} bytes",
        )
    try:
        batch = EventsBatch.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid batch"
        ) from exc

    if not _check_rate(_rate_key(batch, request), time.monotonic()):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
        )

    for event in batch.events:
        if event.event_type not in CLIENT_ALLOWED_EVENTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"event_type not client-allowed: {event.event_type}",
            )

    # Resolve identity without enforcing auth — anon is fine.
    settings = load_settings()
    user = await resolve_user(request, settings, get_user_store())
    user_id = user.id if user is not None else None

    accepted = 0
    with session_scope() as session:
        for event in batch.events:
            try:
                record_event(
                    session,
                    event.event_type,
                    user_id=user_id,
                    anon_id=batch.anon_id,
                    source="client",
                    session_id=batch.session_id,
                    props=event.props,
                )
            except ValueError as exc:
                # Bad props for an otherwise valid type — reject the whole batch.
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
            accepted += 1
    return {"accepted": accepted}
