"""SRT routes. `POST /srt/parse` and `POST /srt/prepare` mounted under `/api`."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pkg_srt_services.api import Cue, ParseError, parse

from .detection import detect

router = APIRouter(prefix="/srt", tags=["srt"])

_MAX_BYTES = 4 * 1024 * 1024  # 4 MiB; slice 1 is sync, keep payloads bounded.
RequiredFile = Annotated[UploadFile, File()]


def _cue_to_dict(cue: Cue) -> dict[str, str | int]:
    return asdict(cue)


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

    try:
        cues = parse(payload)
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return {"cues": [_cue_to_dict(c) for c in cues], "count": len(cues)}


@router.post("/prepare", status_code=status.HTTP_200_OK)
async def prepare_srt(file: RequiredFile) -> dict[str, object]:
    """Parse + detect source language in one shot.

    Same validation and parse as ``POST /srt/parse``, plus a source-language
    suggestion. Returned ``detected_lang`` is ``null`` when detection is
    unmappable or below the confidence floor — the UI then leaves the source
    dropdown unselected for the user to choose.
    """
    payload = await _decode_srt(file)

    try:
        cues = parse(payload)
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    detection = detect(cues)
    return {
        "cues": [_cue_to_dict(c) for c in cues],
        "count": len(cues),
        "detected_lang": detection.lang,
        "confidence": detection.confidence,
    }
