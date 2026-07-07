"""SRT parsing and formatting."""

import re
from dataclasses import dataclass

_TIMESTAMP_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2},\d{3})"
)
_EMPTY_PATTERNS = re.compile(r"^\.{3}|^\s*$")


@dataclass(frozen=True)
class Segment:
    id: int
    start: str
    end: str
    text: str


def parse_srt(content: str) -> list[Segment]:
    blocks = re.split(r"\n{2,}", content.strip())
    segments: list[Segment] = []

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue

        try:
            segment_id = int(lines[0].strip())
        except ValueError:
            continue

        timestamp_match = _TIMESTAMP_RE.match(lines[1].strip())
        if timestamp_match is None:
            continue

        segments.append(
            Segment(
                id=segment_id,
                start=timestamp_match.group(1),
                end=timestamp_match.group(2),
                text="\n".join(lines[2:]).strip(),
            )
        )

    return segments


def preprocess_segments(segments: list[Segment]) -> list[Segment]:
    filtered = [segment for segment in segments if not _EMPTY_PATTERNS.match(segment.text)]
    return [
        Segment(id=new_id, start=segment.start, end=segment.end, text=segment.text)
        for new_id, segment in enumerate(sorted(filtered, key=lambda item: item.id), start=1)
    ]


def format_translated_srt(segments: list[Segment], translations: dict[int, str]) -> str:
    lines: list[str] = []
    for segment in segments:
        lines.append(str(segment.id))
        lines.append(f"{segment.start} --> {segment.end}")
        lines.append(_to_single_line(segment.text))
        translated = translations.get(segment.id)
        if translated:
            lines.append(_to_single_line(translated))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _to_single_line(text: str) -> str:
    return " ".join(line.strip() for line in text.splitlines() if line.strip())
