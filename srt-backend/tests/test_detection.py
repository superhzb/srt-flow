"""Tests for source-language detection (pure module, no I/O)."""

from __future__ import annotations

from pathlib import Path

from pkg_srt_services.api import Cue, parse
from srt_backend.detection import SUPPORTED_LANGS, detect, detect_bilingual


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


def test_detect_bilingual_reference_file() -> None:
    fixture = Path(__file__).parents[2] / "test_files" / "1960-eleves-cours-francais.srt"
    result = detect_bilingual(parse(fixture.read_text(encoding="utf-8")))
    assert result.is_bilingual
    assert result.line_langs == ["fr", "zh"]
    assert result.confidence > 0.5


def test_detect_bilingual_requires_majority_of_all_cues() -> None:
    cues = [
        _cue(1, "This is a complete English sentence.\n这是一个完整的中文句子。"),
        _cue(2, "Another complete English sentence.\n这是另一个完整的中文句子。"),
        _cue(3, "Most of this subtitle file is only English."),
        _cue(4, "The same is true for this subtitle cue."),
        _cue(5, "There are too few bilingual cues to qualify."),
    ]
    assert not detect_bilingual(cues).is_bilingual


def test_detect_bilingual_rejects_wrapped_monolingual_and_single_line_cues() -> None:
    wrapped = [
        _cue(i, "This English caption wraps naturally\nonto a second English line")
        for i in range(1, 4)
    ]
    single = [_cue(i, "This caption has only one line") for i in range(1, 4)]
    assert not detect_bilingual(wrapped).is_bilingual
    assert not detect_bilingual(single).is_bilingual


def test_detect_bilingual_short_lines_detected_via_aggregate() -> None:
    # Each cue's two lines are short enough that per-line detection is
    # unreliable on their own; concatenating line-0 and line-1 gives the
    # detector enough text to recognise the French/English split.
    cues = [
        _cue(i, f"Oui, bien sûr, merci beaucoup.\nYes, of course, thank you so much.")
        for i in range(1, 6)
    ]
    result = detect_bilingual(cues)
    assert result.is_bilingual
    assert result.line_langs == ["fr", "en"]
    assert result.confidence > 0.5
