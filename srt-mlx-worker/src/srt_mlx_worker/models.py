"""HTTP request and response models."""

from typing import TypeGuard

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_lang: str = Field(min_length=1)
    targets: list[str] = Field(min_length=1)
    segments: list[dict[str, object]] = Field(min_length=1)

    @field_validator("targets")
    @classmethod
    def _dedupe_targets(cls, targets: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for target in targets:
            if not target:
                raise ValueError("targets cannot contain empty language codes")
            if target not in seen:
                deduped.append(target)
                seen.add(target)
        return deduped

    @model_validator(mode="after")
    def _validate_segments(self) -> "TranslationRequest":
        seen_ids: set[int] = set()
        required_keys = {"id", self.source_lang}

        for index, segment in enumerate(self.segments):
            keys = set(segment)
            if keys != required_keys:
                raise ValueError(
                    f"segments[{index}] must contain exactly id and {self.source_lang!r}"
                )

            segment_id = segment["id"]
            if not _is_strict_int(segment_id):
                raise ValueError(f"segments[{index}].id must be an integer")
            if segment_id in seen_ids:
                raise ValueError(f"duplicate segment id: {segment_id}")
            seen_ids.add(segment_id)

            text = segment[self.source_lang]
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"segments[{index}].{self.source_lang} must be non-empty text")

        return self


class TranslationResponse(BaseModel):
    source_lang: str
    targets: list[str]
    segments: list[dict[str, object]]


def _is_strict_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)
