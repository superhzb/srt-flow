"""HTTP request and response models."""

from pydantic import BaseModel, ConfigDict, Field


class TranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    srt: str = Field(min_length=1)
    model_path: str | None = None
    batch_size: int | None = Field(default=None, ge=1, le=100)
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    retry_delay: float | None = Field(default=None, ge=0)
    context_window: int | None = Field(default=None, ge=0, le=50)


class TranslationResponse(BaseModel):
    translated_srt: str
