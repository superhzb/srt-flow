"""SRT routes. `POST /srt/parse` and `POST /srt/prepare` mounted under `/api`."""

from __future__ import annotations

import asyncio
import ipaddress
import math
import os
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pkg_srt_services.api import Cue, ParseError, cue_to_dict, parse

from .detection import detect

router = APIRouter(prefix="/srt", tags=["srt"])

_MAX_BYTES = 4 * 1024 * 1024  # 4 MiB; slice 1 is sync, keep payloads bounded.
RequiredFile = Annotated[UploadFile, File()]


class _PrepareLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        now = time.monotonic()
        async with self._lock:
            requests = self._requests[key]
            cutoff = now - self.window_seconds
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.limit:
                retry_after = max(1, math.ceil(requests[0] + self.window_seconds - now))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="prepare request limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            requests.append(now)


def _trusted_proxy(value: str, configured: tuple[str, ...]) -> bool:
    for item in configured:
        if value == item:
            return True
        try:
            if ipaddress.ip_address(value) in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            continue
    return False


def _client_key(request: Request, trusted_proxies: tuple[str, ...]) -> str:
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or not _trusted_proxy(peer, trusted_proxies):
        return peer
    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    for candidate in reversed(chain):
        if not _trusted_proxy(candidate, trusted_proxies):
            return candidate
    return chain[0] if chain else peer


async def _limit_prepare(request: Request) -> None:
    limit = max(1, int(os.environ.get("PREPARE_RATE_LIMIT", "20")))
    window = max(1, int(os.environ.get("PREPARE_RATE_WINDOW_SECONDS", "600")))
    trusted = tuple(
        item.strip()
        for item in os.environ.get(
            "PREPARE_TRUSTED_PROXIES", "testclient,127.0.0.1/32,::1/128"
        ).split(",")
        if item.strip()
    )
    signature = (limit, window)
    limiter = getattr(request.app.state, "prepare_limiter", None)
    if (
        limiter is None
        or getattr(request.app.state, "prepare_limiter_signature", None) != signature
    ):
        limiter = _PrepareLimiter(limit, window)
        request.app.state.prepare_limiter = limiter
        request.app.state.prepare_limiter_signature = signature
    await limiter.check(_client_key(request, trusted))


async def _decode_srt(file: UploadFile) -> str:
    """Shared upload validation + UTF-8 decode for parse / prepare."""
    if not file.filename or not file.filename.lower().endswith(".srt"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file must have a .srt extension",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="uploaded file is empty"
        )
    if len(raw) > _MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"file exceeds {_MAX_BYTES} byte limit",
        )

    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="file is not valid UTF-8",
        ) from exc


def _parse_or_400(payload: str) -> list[Cue]:
    """Parse SRT, mapping ``ParseError`` to a single 400 site."""
    try:
        return parse(payload)
    except ParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/parse", status_code=status.HTTP_200_OK)
async def parse_srt(file: RequiredFile) -> dict[str, object]:
    """Parse an uploaded `.srt` file into cues.

    Accepts `multipart/form-data` with a single `file` field.

    Returns:
        `{"cues": [...], "count": N}` where each cue is
        `{index, start, end, text}`.

    Raises:
        400: Missing/empty file, wrong extension, payload too large, or
            unparseable SRT.
    """
    payload = await _decode_srt(file)
    cues = _parse_or_400(payload)
    return {"cues": [cue_to_dict(c) for c in cues], "count": len(cues)}


@router.post("/prepare", status_code=status.HTTP_200_OK)
async def prepare_srt(request: Request, file: RequiredFile) -> dict[str, object]:
    """Parse + detect source language in one shot.

    Same validation and parse as ``POST /srt/parse``, plus a source-language
    suggestion. Returned ``detected_lang`` is ``null`` when detection is
    unmappable or below the confidence floor — the UI then leaves the source
    dropdown unselected for the user to choose.
    """
    await _limit_prepare(request)
    payload = await _decode_srt(file)
    cues = _parse_or_400(payload)
    detection = detect(cues)
    return {
        "cues": [cue_to_dict(c) for c in cues],
        "count": len(cues),
        "detected_lang": detection.lang,
        "confidence": detection.confidence,
    }
