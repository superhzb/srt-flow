"""FastAPI application factory."""

from fastapi import FastAPI, HTTPException

from .config import TranslationConfig
from .models import TranslationRequest, TranslationResponse
from .prompts import available_languages
from .translator import translate_segments


def create_app(default_config: TranslationConfig | None = None) -> FastAPI:
    config = default_config or TranslationConfig()
    app = FastAPI(title="SRT Cloud Worker", version="0.1.0")

    def translate(request: TranslationRequest) -> TranslationResponse:
        return _translate(request, config)

    app.add_api_route("/health", _health, methods=["GET"])
    app.add_api_route("/languages", lambda: _languages(config), methods=["GET"])
    app.add_api_route(
        "/translate",
        translate,
        methods=["POST"],
        response_model=TranslationResponse,
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
