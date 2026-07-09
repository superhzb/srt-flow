"""Tests for pkg_srt_services.api — only import from package.api."""

from __future__ import annotations

import importlib

import pytest
from pkg_srt_services.api import Cue, ParseError, parse, serialize

SIMPLE = """1
00:00:01,000 --> 00:00:04,074
Hello world

2
00:00:04,074 --> 00:00:07,048
Second cue
spans two lines
"""


def test_public_api_all_names_are_resolvable() -> None:
    mod = importlib.import_module("pkg_srt_services.api")
    for name in mod.__all__:
        assert hasattr(mod, name), f"{name} in __all__ but not defined in api"


def test_parse_simple_two_cues() -> None:
    cues = parse(SIMPLE)
    assert cues == [
        Cue(index=1, start="00:00:01,000", end="00:00:04,074", text="Hello world"),
        Cue(
            index=2,
            start="00:00:04,074",
            end="00:00:07,048",
            text="Second cue\nspans two lines",
        ),
    ]


def test_parse_strips_bom_and_crlf() -> None:
    payload = "\ufeff1\r\n00:00:01,000 --> 00:00:02,000\r\nHi\r\n"
    cues = parse(payload)
    assert cues == [Cue(index=1, start="00:00:01,000", end="00:00:02,000", text="Hi")]


def test_parse_accepts_dot_decimal_separator() -> None:
    cues = parse("1\n00:00:01.000 --> 00:00:02.000\nHi\n")
    assert cues[0].start == "00:00:01.000"
    assert cues[0].end == "00:00:02.000"


def test_parse_empty_raises() -> None:
    with pytest.raises(ParseError):
        parse("")
    with pytest.raises(ParseError):
        parse("   \n\n  ")


def test_parse_missing_timespan_raises() -> None:
    with pytest.raises(ParseError):
        parse("1\nnot a timespan\nHi\n")


def test_parse_missing_text_raises() -> None:
    with pytest.raises(ParseError):
        parse("1\n00:00:01,000 --> 00:00:02,000\n")


def test_parse_bad_index_raises() -> None:
    with pytest.raises(ParseError):
        parse("X\n00:00:01,000 --> 00:00:02,000\nHi\n")


def test_serialize_round_trip() -> None:
    cues = parse(SIMPLE)
    out = serialize(cues)
    # Round trip is stable (modulo the trailing-newline normalisation).
    assert parse(out) == cues


def test_serialize_normalizes_dot_to_comma() -> None:
    cue = Cue(index=1, start="00:00:01.000", end="00:00:02.000", text="Hi")
    assert "00:00:01,000 --> 00:00:02,000" in serialize([cue])


def test_serialize_empty_raises() -> None:
    with pytest.raises(ParseError):
        serialize([])


def test_serialize_empty_text_raises() -> None:
    cue = Cue(index=1, start="00:00:01,000", end="00:00:02,000", text="   ")
    with pytest.raises(ParseError):
        serialize([cue])
