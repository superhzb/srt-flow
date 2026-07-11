"""FastAPI application factory."""

import asyncio
import json
import logging
import queue as queue_mod
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .config import TranslationConfig
from .models import TranslationRequest, TranslationResponse
from .prompts import available_languages
from .translator import BatchProgress, LLMBackend, translate_segments

logger = logging.getLogger(__name__)

_PROGRESS_EVENT = "progress"
_RESULT_EVENT = "result"
_ERROR_EVENT = "error"

TranslateFunc = Callable[
    [
        str,
        list[str],
        list[dict[str, object]],
        TranslationConfig | None,
        None,
        Callable[[BatchProgress], None] | None,
        LLMBackend | None,
    ],
    tuple[list[str], list[dict[str, object]]],
]


def create_app(
    default_config: TranslationConfig | None = None,
    *,
    backend: LLMBackend,
    title: str,
    translate_func: TranslateFunc | None = None,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[Any]] | None = None,
) -> FastAPI:
    config = default_config or TranslationConfig()
    app = FastAPI(title=title, version="0.1.0", lifespan=lifespan)
    active_translate = translate_func or translate_segments

    def translate(request: TranslationRequest) -> TranslationResponse:
        return _translate(request, config, backend, active_translate)

    async def translate_stream(request: TranslationRequest) -> StreamingResponse:
        return await _translate_stream(request, config, backend, active_translate)

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


def _translate(
    request: TranslationRequest,
    config: TranslationConfig,
    backend: LLMBackend,
    translate_func: TranslateFunc,
) -> TranslationResponse:
    try:
        targets, segments = translate_func(
            request.source_lang,
            request.targets,
            request.segments,
            config,
            None,
            None,
            backend,
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
    request: TranslationRequest,
    config: TranslationConfig,
    backend: LLMBackend,
    translate_func: TranslateFunc,
) -> StreamingResponse:
    """Stream translation as NDJSON."""

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
                    targets, segments = translate_func(
                        request.source_lang,
                        request.targets,
                        request.segments,
                        config,
                        None,
                        on_progress,
                        backend,
                    )
                except Exception as exc:  # noqa: BLE001
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
