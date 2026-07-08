"""Translation orchestration."""

import json
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from .config import TranslationConfig
from .llm import ensure_model_available, generate_text
from .prompts import PairConfig, load_lang, load_template, make_pair
from .validation import SourceItem, TranslationItem, ValidationError, parse_and_validate

logger = logging.getLogger(__name__)

Translator = Callable[[str, TranslationConfig], str]


@dataclass(frozen=True)
class BatchProgress:
    """Progress report for one completed top-level batch within one target.

    Attributes:
        target: Target language code (tgt_code of the pair).
        target_index: 0-based index of this target among the supported pairs.
        target_total: Total number of supported targets being translated.
        batch_index: 0-based index of the just-completed top-level batch
            within this target. Sub-splits from binary retry do not advance
            this counter — one increment per top-level batch only.
        batch_total: Total top-level batches for this target
            (= ceil(len(items) / batch_size)).
    """

    target: str
    target_index: int
    target_total: int
    batch_index: int
    batch_total: int


ProgressCallback = Callable[[BatchProgress], None]


def translate_segments(
    source_lang: str,
    targets: list[str],
    segments: list[dict[str, object]],
    config: TranslationConfig | None = None,
    translator: Translator | None = None,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[str], list[dict[str, object]]]:
    active_config = config or TranslationConfig()
    active_translator = translator or _generate_with_mlx
    requested_targets = list(dict.fromkeys(targets))
    src_lang_cfg = load_lang(source_lang, active_config.languages_path)
    if src_lang_cfg is None:
        raise ValueError(f"Unsupported source language: {source_lang}")

    supported_pairs = [
        make_pair(src_lang_cfg, tgt_cfg)
        for target in requested_targets
        if target != source_lang
        and (tgt_cfg := load_lang(target, active_config.languages_path)) is not None
    ]

    unsupported = sorted(set(requested_targets) - {pair.tgt_code for pair in supported_pairs})
    for target in unsupported:
        logger.warning("Skipping unsupported target language: %s", target)

    if not supported_pairs:
        raise ValueError("No requested target is a supported language")

    if translator is None:
        ensure_model_available(active_config.model_path)

    items = [
        {"id": segment["id"], source_lang: segment[source_lang]}
        for segment in segments
    ]
    merged = [dict(item) for item in items]
    by_id = {segment["id"]: segment for segment in merged}

    target_total = len(supported_pairs)
    for target_index, pair in enumerate(supported_pairs):
        translations = _translate_all(
            items,
            pair,
            active_config,
            active_translator,
            target_index=target_index,
            target_total=target_total,
            on_progress=on_progress,
        )
        for item in translations:
            segment = by_id.get(item["id"])
            translated = item.get(pair.tgt_code)
            if segment is not None and isinstance(translated, str):
                segment[pair.tgt_code] = translated

    return [pair.tgt_code for pair in supported_pairs], merged


def _translate_all(
    items: list[SourceItem],
    pair: PairConfig,
    config: TranslationConfig,
    translator: Translator,
    *,
    target_index: int,
    target_total: int,
    on_progress: ProgressCallback | None = None,
) -> list[TranslationItem]:
    translations: list[TranslationItem] = []
    template = load_template(config.template_path)
    batch_total = max(1, math.ceil(len(items) / config.batch_size))

    for batch_index, start in enumerate(range(0, len(items), config.batch_size)):
        batch = items[start : start + config.batch_size]
        context = items[max(0, start - config.context_window) : start]
        translations.extend(
            _translate_with_split(batch, context, pair, config, translator, template)
        )
        if on_progress is not None:
            on_progress(
                BatchProgress(
                    target=pair.tgt_code,
                    target_index=target_index,
                    target_total=target_total,
                    batch_index=batch_index,
                    batch_total=batch_total,
                )
            )

    return translations


def _translate_with_split(
    batch: list[SourceItem],
    context: list[SourceItem],
    pair: PairConfig,
    config: TranslationConfig,
    translator: Translator,
    template: str,
) -> list[TranslationItem]:
    try:
        return _translate_batch(batch, context, pair, config, translator, template)
    except ValidationError as exc:
        if len(batch) == 1:
            logger.warning(
                "Dropping untranslated segment id=%s for target=%s after validation failure: %s",
                batch[0].get("id"),
                pair.tgt_code,
                exc,
            )
            return []

        midpoint = len(batch) // 2
        logger.info(
            "Translation batch failed; splitting into %d and %d",
            midpoint,
            len(batch) - midpoint,
        )
        return _translate_with_split(
            batch[:midpoint],
            context,
            pair,
            config,
            translator,
            template,
        ) + _translate_with_split(
            batch[midpoint:],
            context,
            pair,
            config,
            translator,
            template,
        )


def _translate_batch(
    batch: list[SourceItem],
    context: list[SourceItem],
    pair: PairConfig,
    config: TranslationConfig,
    translator: Translator,
    template: str,
) -> list[TranslationItem]:
    prompt = _build_prompt(batch, context, pair, template)
    last_error: Exception | None = None

    for attempt in range(config.max_retries + 1):
        if attempt > 0:
            time.sleep(config.retry_delay)
        try:
            return parse_and_validate(translator(prompt, config), batch, pair.tgt_code)
        except ValidationError as exc:
            last_error = exc
            logger.warning("Translation attempt %d failed validation: %s", attempt + 1, exc)

    if last_error is not None:
        raise last_error
    raise RuntimeError("Translation failed")


def _build_prompt(
    batch: list[SourceItem],
    context: list[SourceItem],
    pair: PairConfig,
    template: str,
) -> str:
    context_text = "\n".join(str(item[pair.src_code]) for item in context)
    segments_json = json.dumps(batch, ensure_ascii=False)
    return template.format(
        src_lang=pair.src_lang,
        tgt_lang=pair.tgt_lang,
        src_code=pair.src_code,
        tgt_code=pair.tgt_code,
        example_src=pair.example_src,
        example_tgt=pair.example_tgt,
        context=context_text,
        segments=segments_json,
    )


def _generate_with_mlx(prompt: str, config: TranslationConfig) -> str:
    return generate_text(
        prompt=prompt,
        model_path=config.model_path,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
    )
