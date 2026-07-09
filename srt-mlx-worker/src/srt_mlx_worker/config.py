"""Runtime configuration for translation."""

from dataclasses import dataclass

from pkg_translator.api import TranslationConfig as BaseTranslationConfig


@dataclass(frozen=True)
class TranslationConfig(BaseTranslationConfig):
    model_path: str = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    batch_size: int = 10
    max_tokens: int = 2048
