"""Streaming translation client.

Streams NDJSON from a worker's ``/translate/stream``, folds the per-batch
``progress`` events into a single ``[0, 1]`` fraction (denominator =
``Σ batch_total`` across targets, learned from the stream), and returns
the terminal ``result`` segments. Errors/drops raise :class:`WorkerStreamError`.

Pure: no DB, no Storage, no Job. The caller (``worker_loop``) wires
``on_progress`` to a DB write and the result segments to per-target
SRT files on disk. Same NDJSON contract + failure policy as slice 2.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

__all__ = ["StreamOutcome", "WorkerStreamError", "build_segments", "stream_translate"]

logger = logging.getLogger(__name__)


class ProgressUpdate(float):
    """Aggregate-compatible progress value carrying per-target counters."""

    by_target: dict[str, dict[str, int]]

    def __new__(cls, fraction: float, by_target: dict[str, dict[str, int]]) -> ProgressUpdate:
        value = float.__new__(cls, fraction)
        value.by_target = by_target
        return value


ProgressCallback = Callable[[float], None]


@dataclass(frozen=True)
class StreamOutcome:
    """Successful terminal state of a streaming translation."""

    source_lang: str
    targets: list[str]
    segments: list[dict[str, Any]]


class WorkerStreamError(RuntimeError):
    """Raised on any worker-side failure (error event, drop, non-2xx, bad JSON)."""


async def stream_translate(
    worker_base_url: str,
    source_lang: str,
    targets: list[str],
    segments: list[dict[str, Any]],
    on_progress: ProgressCallback | None = None,
) -> StreamOutcome:
    """Stream-translate against one worker.

    Args:
        worker_base_url: Worker root URL (no trailing slash).
        source_lang: Source language code (worker-facing).
        targets: Target language codes.
        segments: Worker-format segments
            ``[{id, "<source_lang>": text}, …]``.
        on_progress: Optional callback fired with a normalised
            ``[0, 1]`` fraction on each ``progress`` event.

    Returns:
        ``StreamOutcome`` on a terminal ``result`` event.

    Raises:
        WorkerStreamError: On any failure — error event, dropped
            connection, non-2xx open, malformed JSON, or stream ending
            without a terminal event.
    """
    body: dict[str, Any] = {
        "source_lang": source_lang,
        "targets": targets,
        "segments": segments,
    }

    progress_by_target: dict[str, dict[str, int]] = {}
    seen_targets: set[str] = set()
    batches_done = 0
    batches_total_sum = 0

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", f"{worker_base_url}/translate/stream", json=body
            ) as resp:
                if resp.status_code != 200:
                    detail = await _safe_text(resp)
                    raise WorkerStreamError(f"worker opened {resp.status_code}: {detail}")

                terminal = False
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    event = json.loads(line)
                    etype = event.get("event")
                    if etype == "progress":
                        target_index = int(event["target_index"])
                        target = str(event.get("target", targets[target_index]))
                        total = int(event["batch_total"])
                        previous_done = progress_by_target.get(target, {}).get("done", 0)
                        done = int(event.get("batch_index", previous_done)) + 1
                        progress_by_target[target] = {
                            "done": done,
                            "total": total,
                        }
                        if target not in seen_targets:
                            seen_targets.add(target)
                            batches_total_sum += total
                        batches_done += 1
                        if on_progress is not None:
                            fraction = (
                                batches_done / batches_total_sum if batches_total_sum else 0.0
                            )
                            on_progress(ProgressUpdate(fraction, dict(progress_by_target)))
                    elif etype == "result":
                        outcome = StreamOutcome(
                            source_lang=str(event.get("source_lang", source_lang)),
                            targets=list(event.get("targets", targets)),
                            segments=list(event.get("segments", [])),
                        )
                        if on_progress is not None:
                            completed = {
                                target: {
                                    "done": progress_by_target.get(target, {}).get("total", 1),
                                    "total": progress_by_target.get(target, {}).get("total", 1),
                                }
                                for target in outcome.targets
                            }
                            on_progress(ProgressUpdate(1.0, completed))
                        terminal = True
                        return outcome
                    elif etype == "error":
                        raise WorkerStreamError(str(event.get("detail", "worker error")))
                    else:
                        logger.warning("unknown stream event: %r", event)

                if not terminal:
                    raise WorkerStreamError("worker stream ended without a terminal event")
    except WorkerStreamError:
        raise
    except (httpx.HTTPError, OSError) as exc:
        raise WorkerStreamError(f"connection error: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 — wrap JSON/network oddities
        raise WorkerStreamError(f"stream failed: {exc}") from exc

    # Unreachable: every branch above either returns or raises.
    raise WorkerStreamError("stream_translate fell through unexpectedly")


async def _safe_text(resp: httpx.Response) -> str:
    try:
        return (await resp.aread()).decode("utf-8", errors="replace")[:200]
    except Exception:  # noqa: BLE001
        return "<unreadable>"


# Adapter helper — shared by routes (POST validation) and orchestration.
def build_segments(cues: list[Any], source_lang: str) -> list[dict[str, Any]]:
    """Map cues → worker ``segments`` format: ``[{id, "<src>": text}]``."""
    return [{"id": cue.index, source_lang: cue.text} for cue in cues]
