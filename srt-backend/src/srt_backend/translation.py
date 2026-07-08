"""Background translation: stream worker ``/translate/stream``, fold progress.

Pure-ish orchestration: takes a ``Job`` to mutate, the worker base URL, and
the parsed cues + language choices. Emits SRT results per target on success.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

import httpx2
from pkg_srt_services.api import Cue, serialize

from .jobs import Job

__all__ = ["run_translation"]

logger = logging.getLogger(__name__)


async def run_translation(
    job: Job,
    cues: list[Cue],
    source_lang: str,
    targets: list[str],
    worker_base_url: str,
) -> None:
    """Stream-translate against one worker and update ``job`` in-place.

    Failure policy (per PLAN.md): any error event, dropped/timed-out
    connection, or non-2xx open → ``job.status = "failed"`` with detail;
    partial results are discarded (all-or-nothing).
    """
    job.status = "processing"
    segments = [{"id": cue.index, source_lang: cue.text} for cue in cues]
    body: dict[str, Any] = {
        "source_lang": source_lang,
        "targets": targets,
        "segments": segments,
    }

    batches_done = 0
    batches_total_sum = 0
    seen_targets: set[int] = set()

    try:
        async with httpx2.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", f"{worker_base_url}/translate/stream", json=body
            ) as resp:
                if resp.status_code != 200:
                    detail = await _safe_text(resp)
                    _fail(job, f"worker opened {resp.status_code}: {detail}")
                    return

                terminal = False
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    etype = event.get("event")
                    if etype == "progress":
                        ti = int(event["target_index"])
                        if ti not in seen_targets:
                            seen_targets.add(ti)
                            batches_total_sum += int(event["batch_total"])
                        batches_done += 1
                        job.progress = (
                            batches_done / batches_total_sum
                            if batches_total_sum > 0
                            else 0.0
                        )
                    elif etype == "result":
                        job.results = _build_results(
                            cues, event["targets"], event["segments"]
                        )
                        job.progress = 1.0
                        job.status = "done"
                        terminal = True
                        return
                    elif etype == "error":
                        _fail(job, str(event.get("detail", "worker error")))
                        terminal = True
                        return
                    else:
                        logger.warning("unknown stream event: %r", event)

                if not terminal:
                    _fail(job, "worker stream ended without a terminal event")
    except (httpx2.HTTPError, OSError) as exc:
        _fail(job, f"connection error: {exc}")
    except Exception as exc:  # noqa: BLE001 — never let the task die silently
        logger.exception("translation task crashed")
        _fail(job, f"internal error: {exc}")


def _fail(job: Job, message: str) -> None:
    job.status = "failed"
    job.error = message
    job.results = None


async def _safe_text(resp: httpx2.Response) -> str:
    try:
        return (await resp.aread()).decode("utf-8", errors="replace")[:200]
    except Exception:  # noqa: BLE001
        return "<unreadable>"


def _build_results(
    cues: list[Cue],
    targets: list[str],
    segments: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Per-target SRT: clone cues, swap text with translated text by id."""
    by_id: dict[int, dict[str, Any]] = {
        int(seg["id"]): seg for seg in segments if "id" in seg
    }
    results: list[dict[str, str]] = []
    for tgt in targets:
        translated: list[Cue] = []
        for cue in cues:
            entry = by_id.get(cue.index)
            text = entry.get(tgt) if entry else None
            translated.append(
                cue if not isinstance(text, str) else dataclasses.replace(cue, text=text)
            )
        results.append({"lang": tgt, "srt": serialize(translated)})
    return results
