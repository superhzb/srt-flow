"""Prompt template and language registry."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import yaml


@dataclass(frozen=True)
class LangConfig:
    lang_code: str
    lang_name: str
    example: str


@dataclass(frozen=True)
class PairConfig:
    src_code: str
    tgt_code: str
    src_lang: str
    tgt_lang: str
    example_src: str
    example_tgt: str


def load_lang(code: str, languages_path: str) -> LangConfig | None:
    return _load_langs(str(Path(languages_path).resolve())).get(code)


def make_pair(src: LangConfig, tgt: LangConfig) -> PairConfig:
    return PairConfig(
        src_code=src.lang_code,
        tgt_code=tgt.lang_code,
        src_lang=src.lang_name,
        tgt_lang=tgt.lang_name,
        example_src=src.example,
        example_tgt=tgt.example,
    )


def load_template(template_path: str) -> str:
    return _load_template(str(Path(template_path).resolve()))


def available_languages(languages_path: str) -> list[dict[str, str]]:
    langs = _load_langs(str(Path(languages_path).resolve()))
    return [
        {"code": lang.lang_code, "name": lang.lang_name}
        for lang in sorted(langs.values(), key=lambda lang: lang.lang_code)
    ]


@lru_cache
def _load_template(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


@lru_cache
def _load_langs(path: str) -> dict[str, LangConfig]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("languages.yaml must contain a languages list")
    data = cast(dict[str, object], raw)
    raw_langs = data.get("languages")
    if not isinstance(raw_langs, list):
        raise ValueError("languages.yaml must contain a languages list")

    langs: dict[str, LangConfig] = {}
    for index, item in enumerate(cast(list[object], raw_langs)):
        if not isinstance(item, dict):
            raise ValueError(f"languages[{index}] must be a mapping")
        lang = _parse_lang(cast(dict[str, Any], item), index)
        if lang.lang_code in langs:
            raise ValueError(f"duplicate language code: {lang.lang_code}")
        langs[lang.lang_code] = lang

    return langs


def _parse_lang(item: dict[str, Any], index: int) -> LangConfig:
    required = ("lang_code", "lang_name", "example")
    values: dict[str, str] = {}
    for key in required:
        value = item.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"languages[{index}].{key} must be a non-empty string")
        values[key] = value

    return LangConfig(
        lang_code=values["lang_code"],
        lang_name=values["lang_name"],
        example=values["example"],
    )
