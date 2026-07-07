"""Parse and validate model translation output."""

import json
import re
from collections.abc import Mapping
from typing import TypedDict, TypeGuard, cast

_SMART_QUOTE_MAP = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})
_STATS_RE = re.compile(r"^[\d\s,.\-:;]+$")


class ValidationError(Exception):
    """Raised when a model response does not match the expected translation shape."""


class TranslationItem(TypedDict):
    id: int
    zh: str


class SourceItem(TypedDict):
    id: int
    fr: str


def parse_and_validate(raw: str, batch: list[SourceItem]) -> list[TranslationItem]:
    parsed = _extract_json_array(raw)
    if len(parsed) != len(batch):
        raise ValidationError(f"Length mismatch: expected {len(batch)}, got {len(parsed)}")

    results: list[TranslationItem] = []
    for item, expected in zip(parsed, batch, strict=True):
        if not _is_translation_item(item):
            raise ValidationError(f"Item is not a valid translation object: {item!r}")
        if item["id"] != expected["id"]:
            raise ValidationError(f"ID mismatch: expected {expected['id']}, got {item['id']}")
        if not _is_valid_translation(item["zh"]):
            raise ValidationError(f"Invalid translation for id={item['id']}: {item['zh']!r}")

        results.append(item)

    return results


def _extract_json_array(raw: str) -> list[object]:
    sanitized = raw.translate(_SMART_QUOTE_MAP)
    try:
        parsed = json.loads(sanitized)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return cast(list[object], parsed)

    match = re.search(r"\[.*\]", sanitized, re.DOTALL)
    if match is not None:
        try:
            extracted = json.loads(match.group())
        except json.JSONDecodeError:
            extracted = None
        if isinstance(extracted, list):
            return cast(list[object], extracted)

    raise ValidationError("JSON parse failed")


def _is_translation_item(value: object) -> TypeGuard[TranslationItem]:
    if not isinstance(value, dict):
        return False
    mapping = cast(Mapping[object, object], value)
    return (
        isinstance(mapping.get("id"), int)
        and isinstance(mapping.get("zh"), str)
    )


def _is_valid_translation(value: str) -> bool:
    stripped = value.strip()
    return bool(stripped) and (bool(_STATS_RE.match(stripped)) or len(stripped) > 0)
