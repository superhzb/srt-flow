"""Parse and validate model translation output."""

import json
import re
from collections.abc import Mapping
from typing import TypeGuard, cast

_SMART_QUOTE_MAP = str.maketrans({"\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'"})


class ValidationError(Exception):
    """Raised when a model response does not match the expected translation shape."""


SourceItem = dict[str, object]
TranslationItem = dict[str, object]


def parse_and_validate(
    raw: str,
    batch: list[SourceItem],
    target_lang: str,
) -> list[TranslationItem]:
    parsed = _extract_json_array(raw)
    if len(parsed) != len(batch):
        raise ValidationError(f"Length mismatch: expected {len(batch)}, got {len(parsed)}")

    results: list[TranslationItem] = []
    for item, expected in zip(parsed, batch, strict=True):
        if not _is_translation_item(item, target_lang):
            raise ValidationError(f"Item is not a valid translation object: {item!r}")
        if item["id"] != expected["id"]:
            raise ValidationError(f"ID mismatch: expected {expected['id']}, got {item['id']}")
        translation = item[target_lang]
        if not isinstance(translation, str) or not _is_valid_translation(translation):
            raise ValidationError(f"Invalid translation for id={item['id']}: {translation!r}")

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


def _is_translation_item(value: object, target_lang: str) -> TypeGuard[TranslationItem]:
    if not isinstance(value, dict):
        return False
    mapping = cast(Mapping[object, object], value)
    return _is_strict_int(mapping.get("id")) and isinstance(mapping.get(target_lang), str)


def _is_valid_translation(value: str) -> bool:
    return bool(value.strip())


def _is_strict_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)
