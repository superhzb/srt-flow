"""Direct tests for ``worker_client.stream_translate``.

The streaming client (~100 lines of NDJSON folding + error policy) previously
had NO direct test — ``FakeWorkerClient`` bypassed it entirely. These tests
drive the real HTTP path via an in-process ASGI app over ``httpx.ASGITransport``
(no socket), covering: progress-denominator folding, the terminal ``result``
event, ``error`` events, non-2xx open, and a stream that ends without a
terminal event.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, StreamingResponse
from pkg_job_orch import worker_client
from pkg_job_orch.worker_client import (
    StreamOutcome,
    WorkerStreamError,
    stream_translate,
)


def _ndjson_app(lines: list[dict[str, Any]], *, status_code: int = 200) -> FastAPI:
    """Build an app whose ``/translate/stream`` emits ``lines`` as NDJSON."""
    app = FastAPI()

    @app.post("/translate/stream")
    async def stream() -> StreamingResponse:  # pyright: ignore[reportUnusedFunction]
        async def gen() -> AsyncGenerator[str, None]:
            for line in lines:
                yield json.dumps(line) + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson", status_code=status_code)

    return app


@pytest.fixture
def patched_client(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Patch ``stream_translate``'s httpx.AsyncClient to route to an ASGI app."""

    def install(app: FastAPI) -> None:
        real_async_client = httpx.AsyncClient

        def factory(*_args: Any, **kwargs: Any) -> httpx.AsyncClient:
            kwargs.pop("timeout", None)
            return real_async_client(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testworker",
                **kwargs,
            )

        monkeypatch.setattr(worker_client.httpx, "AsyncClient", factory)

    return install


async def test_progress_denominator_folds_across_targets(patched_client: Any) -> None:
    """Progress fraction uses ``Σ batch_total`` across targets, learned from stream.

    target 0 batch_total=2, target 1 batch_total=3 → denominator 5 once both
    seen. Note the fraction can *decrease* when a new target widens the
    denominator (1.0 after target 0's 2/2, then 3/5 after target 1 lands).
    """
    lines = [
        {"event": "progress", "target_index": 0, "batch_total": 2},
        {"event": "progress", "target_index": 0, "batch_total": 2},
        {"event": "progress", "target_index": 1, "batch_total": 3},
        {"event": "progress", "target_index": 1, "batch_total": 3},
        {"event": "progress", "target_index": 1, "batch_total": 3},
        {
            "event": "result",
            "source_lang": "en",
            "targets": ["es", "fr"],
            "segments": [{"id": 0, "es": "hola", "fr": "bonjour"}],
        },
    ]
    patched_client(_ndjson_app(lines))

    fractions: list[float] = []
    outcome = await stream_translate(
        "http://testworker",
        "en",
        ["es", "fr"],
        [{"id": 0, "en": "hello"}],
        on_progress=fractions.append,
    )

    assert isinstance(outcome, StreamOutcome)
    assert outcome.targets == ["es", "fr"]
    assert outcome.segments == [{"id": 0, "es": "hola", "fr": "bonjour"}]
    # 5 progress folds + the terminal 1.0 emitted by the result event.
    assert fractions == [0.5, 1.0, 0.6, 0.8, 1.0, 1.0]


async def test_error_event_raises(patched_client: Any) -> None:
    lines = [
        {"event": "progress", "target_index": 0, "batch_total": 1},
        {"event": "error", "detail": "model exploded"},
    ]
    patched_client(_ndjson_app(lines))

    with pytest.raises(WorkerStreamError, match="model exploded"):
        await stream_translate("http://testworker", "en", ["es"], [{"id": 0, "en": "hi"}])


async def test_non_200_open_raises(patched_client: Any) -> None:
    # App that returns 503 with a plain-text body.
    app = FastAPI()

    @app.post("/translate/stream")
    async def busy() -> Any:  # pyright: ignore[reportUnusedFunction]
        return PlainTextResponse("worker overloaded", status_code=503)

    patched_client(app)

    with pytest.raises(WorkerStreamError, match="worker opened 503"):
        await stream_translate("http://testworker", "en", ["es"], [{"id": 0, "en": "hi"}])


async def test_stream_ends_without_terminal_raises(patched_client: Any) -> None:
    # Only progress events, then the stream closes — no result/error.
    lines = [
        {"event": "progress", "target_index": 0, "batch_total": 1},
        {"event": "progress", "target_index": 0, "batch_total": 1},
    ]
    patched_client(_ndjson_app(lines))

    with pytest.raises(WorkerStreamError, match="ended without a terminal event"):
        await stream_translate("http://testworker", "en", ["es"], [{"id": 0, "en": "hi"}])


async def test_default_error_detail_when_missing(patched_client: Any) -> None:
    # An ``error`` event without a ``detail`` falls back to the generic message.
    patched_client(_ndjson_app([{"event": "error"}]))

    with pytest.raises(WorkerStreamError, match="worker error"):
        await stream_translate("http://testworker", "en", ["es"], [{"id": 0, "en": "hi"}])
