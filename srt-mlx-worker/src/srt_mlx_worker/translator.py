"""SRT translation orchestration."""

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from .config import TranslationConfig
from .llm import generate_text
from .srt import format_translated_srt, parse_srt, preprocess_segments
from .validation import SourceItem, TranslationItem, ValidationError, parse_and_validate

logger = logging.getLogger(__name__)

Translator = Callable[[str, TranslationConfig], str]
_PROMPT_PATH = Path(__file__).with_name("prompt.txt")


def translate_srt_text(
    content: str,
    config: TranslationConfig | None = None,
    translator: Translator | None = None,
) -> str:
    active_config = config or TranslationConfig()
    active_translator = translator or _generate_with_mlx

    segments = preprocess_segments(parse_srt(content))
    if not segments:
        raise ValueError("No valid SRT segments found")

    items = [SourceItem(id=segment.id, fr=segment.text) for segment in segments]
    translations = _translate_all(items, active_config, active_translator)
    return format_translated_srt(segments, translations)


def _translate_all(
    items: list[SourceItem],
    config: TranslationConfig,
    translator: Translator,
) -> dict[int, str]:
    translations: dict[int, str] = {}
    template = _PROMPT_PATH.read_text(encoding="utf-8")

    for start in range(0, len(items), config.batch_size):
        batch = items[start : start + config.batch_size]
        context = items[max(0, start - config.context_window) : start]
        results = _translate_with_split(batch, context, config, translator, template)
        for item in results:
            translations[item["id"]] = item["zh"]

    return translations


def _translate_with_split(
    batch: list[SourceItem],
    context: list[SourceItem],
    config: TranslationConfig,
    translator: Translator,
    template: str,
) -> list[TranslationItem]:
    try:
        return _translate_batch(batch, context, config, translator, template)
    except Exception:
        if len(batch) == 1:
            raise

        midpoint = len(batch) // 2
        logger.info(
            "Translation batch failed; splitting into %d and %d",
            midpoint,
            len(batch) - midpoint,
        )
        return _translate_with_split(
            batch[:midpoint],
            context,
            config,
            translator,
            template,
        ) + _translate_with_split(
            batch[midpoint:],
            context,
            config,
            translator,
            template,
        )


def _translate_batch(
    batch: list[SourceItem],
    context: list[SourceItem],
    config: TranslationConfig,
    translator: Translator,
    template: str,
) -> list[TranslationItem]:
    prompt = _build_prompt(batch, context, template)
    last_error: Exception | None = None

    for attempt in range(config.max_retries + 1):
        if attempt > 0:
            time.sleep(config.retry_delay)
        try:
            return parse_and_validate(translator(prompt, config), batch)
        except ValidationError as exc:
            last_error = exc
            logger.warning("Translation attempt %d failed validation: %s", attempt + 1, exc)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Translation failed")


def _build_prompt(
    batch: list[SourceItem],
    context: list[SourceItem],
    template: str,
) -> str:
    context_text = "\n".join(str(item["fr"]) for item in context)
    segments_json = json.dumps(batch, ensure_ascii=False)
    return template.format(context=context_text, segments=segments_json)


def _generate_with_mlx(prompt: str, config: TranslationConfig) -> str:
    return generate_text(
        prompt=prompt,
        model_path=config.model_path,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )
