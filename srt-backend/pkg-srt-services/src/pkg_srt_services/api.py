"""Public API for pkg_srt_services.

Pure parse/serialize for SubRip (.srt) subtitle files. No network, no I/O.

A cue is one subtitle block: index, start timestamp, end timestamp, and the
caption text (one or more lines, trailing newline stripped).

Timestamps are kept as their raw SubRip strings (`HH:MM:SS,mmm`) so the wire
format round-trips byte-for-byte through `serialize(parse(s))`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Cue", "ParseError", "parse", "serialize"]

_TIMESTAMP = r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}"
_TIMESPAN = re.compile(rf"^\s*({_TIMESTAMP})\s*-->\s*({_TIMESTAMP})\s*$")
_INDEX = re.compile(r"^\s*(\d+)\s*$")


class ParseError(ValueError):
    """Raised when an SRT payload cannot be parsed."""


@dataclass(frozen=True)
class Cue:
    """One subtitle cue.

    Attributes:
        index: SubRip sequence number as it appears in the file (1-based).
        start: Start timestamp, SubRip form `HH:MM:SS,mmm`.
        end: End timestamp, SubRip form `HH:MM:SS,mmm`.
        text: Caption body. Newlines preserved; surrounding whitespace stripped.
    """

    index: int
    start: str
    end: str
    text: str


def parse(payload: str) -> list[Cue]:
    """Parse an SRT payload into cues.

    Args:
        payload: Raw .srt text (UTF-8). BOM is tolerated at the start.

    Returns:
        Cues in document order.

    Raises:
        ParseError: If the payload is empty or any block is malformed.
    """
    if not payload or not payload.strip():
        raise ParseError("empty SRT payload")

    text = payload.lstrip("\ufeff")
    # Normalize CRLF/CR to LF so block splitting is line-ending agnostic.
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Split on one-or-more blank lines; trailing empties dropped.
    blocks = [b for b in re.split(r"\n\s*\n", normalized.strip()) if b.strip()]

    cues: list[Cue] = []
    for block in blocks:
        cues.append(_parse_block(block))

    if not cues:
        raise ParseError("no cues found in SRT payload")
    return cues


def _parse_block(block: str) -> Cue:
    lines = block.split("\n")
    if len(lines) < 2:
        raise ParseError(f"cue block too short: {block!r}")

    idx_match = _INDEX.match(lines[0])
    if idx_match is None:
        raise ParseError(f"missing/invalid cue index line: {lines[0]!r}")
    index = int(idx_match.group(1))

    span_match = _TIMESPAN.match(lines[1])
    if span_match is None:
        raise ParseError(f"missing/invalid timespan line: {lines[1]!r}")
    start, end = span_match.group(1), span_match.group(2)

    body = "\n".join(lines[2:]).strip()
    if not body:
        raise ParseError(f"cue {index} has empty text")

    return Cue(index=index, start=start, end=end, text=body)


def serialize(cues: list[Cue]) -> str:
    """Serialize cues back to SubRip (.srt) text.

    Timestamps are emitted in canonical SubRip form (`,` decimal separator)
    regardless of the input's separator.

    Args:
        cues: Cues to serialize. Caller is responsible for sequence numbering
            (indices are emitted as given, not rewritten).

    Returns:
        SRT text with blocks joined by a single blank line, trailing newline
        included.

    Raises:
        ParseError: If a cue's timestamp is not a valid SubRip timestamp.
    """
    if not cues:
        raise ParseError("cannot serialize empty cue list")

    out: list[str] = []
    for cue in cues:
        start = _canonical_ts(cue.start)
        end = _canonical_ts(cue.end)
        if not cue.text.strip():
            raise ParseError(f"cue {cue.index} has empty text")
        out.append(f"{cue.index}\n{start} --> {end}\n{cue.text}")

    return "\n\n".join(out) + "\n"


def _canonical_ts(ts: str) -> str:
    m = re.fullmatch(_TIMESTAMP, ts)
    if m is None:
        raise ParseError(f"invalid timestamp: {ts!r}")
    return ts.replace(".", ",")
