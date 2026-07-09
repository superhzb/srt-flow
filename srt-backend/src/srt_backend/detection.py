"""Source-language detection for parsed SRT cues.

Lingua detects the language family; for Chinese we then run a
Simplified/Traditional character heuristic to pick between ``zh`` and
``zh-TW``. Result is a *suggestion* the user can override in the UI.

Pure (no FastAPI, no I/O) so it is testable in isolation.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import cast

import hanzidentifier  # type: ignore[import-not-found,import-untyped]
from lingua import Language, LanguageDetector, LanguageDetectorBuilder
from pkg_srt_services.api import Cue

__all__ = ["Detection", "detect", "SUPPORTED_LANGS"]

# hanzidentifier ships no type stubs; treat its one used helper as `str -> bool`.
_is_traditional: Callable[[str], bool] = cast(
    "Callable[[str], bool]", hanzidentifier.is_traditional  # type: ignore[no-any-return]
)

# Worker-supported target/source codes (kept in sync with both workers'
# languages.yaml). Detection only ever returns codes from this set or None.
SUPPORTED_LANGS: frozenset[str] = frozenset(
    {"en", "es", "zh", "zh-TW", "fr", "de", "ja", "ko"}
)

_CONFIDENCE_FLOOR: float = 0.5
_SAMPLE_SIZE: int = 40

# Only the languages we can map to worker codes are loaded into the detector
# — this both speeds detection and prevents returning unsupported codes.
_LINGUA_LANGS: tuple[Language, ...] = (
    Language.ENGLISH,
    Language.SPANISH,
    Language.FRENCH,
    Language.GERMAN,
    Language.JAPANESE,
    Language.KOREAN,
    Language.CHINESE,
)

# Lingua Language → worker code. Chinese is split downstream.
_LINGUA_TO_CODE: dict[Language, str] = {
    Language.ENGLISH: "en",
    Language.SPANISH: "es",
    Language.FRENCH: "fr",
    Language.GERMAN: "de",
    Language.JAPANESE: "ja",
    Language.KOREAN: "ko",
    Language.CHINESE: "zh",
}

# Module-level detector: lingua's builder is expensive to construct, the
# built detector is stateless and safe to reuse. Built lazily on first use
# (honors the repo "no import side-effects" rule) via an lru_cache accessor.
@lru_cache(maxsize=1)
def _get_detector() -> LanguageDetector:
    return LanguageDetectorBuilder.from_languages(*_LINGUA_LANGS).build()


@dataclass(frozen=True)
class Detection:
    """Result of source-language detection.

    Attributes:
        lang: Worker-supported code, or ``None`` if no confident guess.
        confidence: Top-1 lingua confidence in [0, 1]. Reported even when
            ``lang`` is ``None`` (e.g. below the floor) so the UI can show
            "best guess was X with Y% but below threshold".
    """

    lang: str | None
    confidence: float


def detect(cues: list[Cue]) -> Detection:
    """Detect the source language from a sample of cue text.

    Samples up to ``_SAMPLE_SIZE`` non-empty cue texts, joins them, and asks
    lingua for confidence values. Returns ``Detection(None, ...)`` when:
      - there is no non-empty cue text,
      - the top guess is not mappable to a supported code,
      - or the top confidence is below ``_CONFIDENCE_FLOOR``.

    For Chinese, runs ``hanzidentifier`` on the sample: Traditional-only
    characters → ``zh-TW``; otherwise ``zh`` (shared or Simplified-only).
    """
    texts = [c.text for c in cues if c.text.strip()][:_SAMPLE_SIZE]
    if not texts:
        return Detection(lang=None, confidence=0.0)

    sample = " ".join(texts)
    values = _get_detector().compute_language_confidence_values(sample)
    if not values:
        return Detection(lang=None, confidence=0.0)

    top = values[0]
    confidence = float(top.value)
    code = _LINGUA_TO_CODE.get(top.language)
    if code is None or confidence < _CONFIDENCE_FLOOR:
        return Detection(lang=None, confidence=confidence)

    if code == "zh" and _is_traditional(sample):
        code = "zh-TW"

    return Detection(lang=code, confidence=confidence)
