"""FastAPI application factory."""

from dataclasses import replace

from fastapi import FastAPI, HTTPException

from .config import TranslationConfig
from .models import TranslationRequest, TranslationResponse
from .translator import translate_srt_text


def create_app(default_config: TranslationConfig | None = None) -> FastAPI:
    config = default_config or TranslationConfig()
    app = FastAPI(title="SRT MLX Worker", version="0.1.0")

    def translate(request: TranslationRequest) -> TranslationResponse:
        return _translate(request, config)

    app.add_api_route("/health", _health, methods=["GET"])
    app.add_api_route(
        "/translate",
        translate,
        methods=["POST"],
        response_model=TranslationResponse,
    )
    return app


def _health() -> dict[str, str]:
    return {"status": "ok"}


def _translate(request: TranslationRequest, config: TranslationConfig) -> TranslationResponse:
    try:
        translated = translate_srt_text(request.srt, config=_merge_config(config, request))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return TranslationResponse(translated_srt=translated)


def _merge_config(config: TranslationConfig, request: TranslationRequest) -> TranslationConfig:
    overrides = request.model_dump(exclude={"srt"}, exclude_none=True)
    return replace(config, **overrides)
