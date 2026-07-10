"""Unauthenticated deployment readiness endpoint."""

from __future__ import annotations

import os

from fastapi import APIRouter

__all__ = ["router"]

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Report process readiness and the source commit running this process."""
    return {
        "status": "ok",
        "commit": os.environ.get("SRT_FLOW_COMMIT", "unknown"),
    }
