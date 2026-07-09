"""Tests for source-language detection (pure module, no I/O)."""

from __future__ import annotations

from pkg_srt_services.api import Cue
from srt_backend.detection import SUPPORTED_LANGS, detect


def _cue(index: int, text: str) -> Cue:
    return Cue(index=index, start="00:00:01,000", end="00:00:02,000", text=text)


def test_detect_english() -> None:
    cues = [
        _cue(1, "It takes real strength to make it all the way to the end."),
        _cue(2, "You have to be brave enough to face what comes next."),
    ]
    d = detect(cues)
    assert d.lang == "en"
    assert d.confidence >= 0.5


def test_detect_simplified_chinese_picks_zh() -> None:
    d = detect([_cue(1, "而且要走到最后，真的需要很强")])
    assert d.lang == "zh"
    assert d.confidence >= 0.5


def test_detect_traditional_chinese_picks_zh_tw() -> None:
    d = detect([_cue(1, "而且要走到最後，真的需要很強")])
    assert d.lang == "zh-TW"
    assert d.confidence >= 0.5


def test_detect_french() -> None:
    d = detect([_cue(1, "Et il faut être vraiment fort pour aller jusqu'au bout.")])
    assert d.lang == "fr"


def test_detect_returns_none_on_empty_or_blank_text() -> None:
    assert detect([]).lang is None
    assert detect([_cue(1, "   ")]).lang is None


def test_detected_lang_is_always_supported() -> None:
    # Sanity: any successful detection lands in the supported set.
    samples = [
        [Cue(1, "a", "b", "Hello there, how are you today my friend?")],
        [Cue(1, "a", "b", "Et il faut être vraiment fort pour aller jusqu'au bout.")],
    ]
    for cues in samples:
        d = detect(cues)
        assert d.lang is None or d.lang in SUPPORTED_LANGS
