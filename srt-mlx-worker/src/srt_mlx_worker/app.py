"""FastAPI application factory."""

import asyncio
import json
import logging
import queue as queue_mod
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .config import TranslationConfig
from .models import TranslationRequest, TranslationResponse
from .prompts import available_languages
from .translator import BatchProgress, translate_segments

logger = logging.getLogger(__name__)

_PROGRESS_EVENT = "progress"
_RESULT_EVENT = "result"
_ERROR_EVENT = "error"


def create_app(default_config: TranslationConfig | None = None) -> FastAPI:
    config = default_config or TranslationConfig()
    app = FastAPI(title="SRT MLX Worker", version="0.1.0")

    def translate(request: TranslationRequest) -> TranslationResponse:
        return _translate(request, config)

    async def translate_stream(request: TranslationRequest) -> StreamingResponse:
        return await _translate_stream(request, config)

    app.add_api_route("/health", _health, methods=["GET"])
    app.add_api_route("/languages", lambda: _languages(config), methods=["GET"])
    app.add_api_route(
        "/translate",
        translate,
        methods=["POST"],
        response_model=TranslationResponse,
    )
    app.add_api_route(
        "/translate/stream",
        translate_stream,
        methods=["POST"],
        responses={200: {"content": {"application/x-ndjson": {}}}},
    )
    return app


def _health() -> dict[str, str]:
    return {"status": "ok"}


def _languages(config: TranslationConfig) -> dict[str, list[dict[str, str]]]:
    return {"languages": available_languages(config.languages_path)}


def _translate(request: TranslationRequest, config: TranslationConfig) -> TranslationResponse:
    try:
        targets, segments = translate_segments(
            request.source_lang,
            request.targets,
            request.segments,
            config=config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TranslationResponse(
        source_lang=request.source_lang,
        targets=targets,
        segments=segments,
    )


async def _translate_stream(
    request: TranslationRequest, config: TranslationConfig
) -> StreamingResponse:
    """Stream translation as NDJSON.

    Emits one ``progress`` event per top-level batch, then a terminal
    ``result`` (or ``error``) event. Exactly one terminal event closes the
    stream.
    """

    async def gen() -> AsyncIterator[bytes]:
        q: queue_mod.Queue[dict[str, Any] | None] = queue_mod.Queue()

        def work() -> None:
            def on_progress(p: BatchProgress) -> None:
                q.put(
                    {
                        "event": _PROGRESS_EVENT,
                        "target": p.target,
                        "target_index": p.target_index,
                        "target_total": p.target_total,
                        "batch_index": p.batch_index,
                        "batch_total": p.batch_total,
                    }
                )

            try:
                try:
                    targets, segments = translate_segments(
                        request.source_lang,
                        request.targets,
                        request.segments,
                        config=config,
                        on_progress=on_progress,
                    )
                except Exception as exc:  # noqa: BLE001 — surface any failure to stream
                    logger.warning("translate/stream failed: %s", exc)
                    q.put({"event": _ERROR_EVENT, "detail": str(exc)})
                    return
                q.put(
                    {
                        "event": _RESULT_EVENT,
                        "source_lang": request.source_lang,
                        "targets": targets,
                        "segments": segments,
                    }
                )
            finally:
                q.put(None)

        task = asyncio.create_task(asyncio.to_thread(work))
        try:
            while True:
                item = await asyncio.to_thread(q.get, True, None)
                if item is None:
                    break
                yield (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8")
        finally:
            await task

    return StreamingResponse(gen(), media_type="application/x-ndjson")
