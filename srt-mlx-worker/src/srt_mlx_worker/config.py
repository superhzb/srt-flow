"""Runtime configuration for SRT translation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TranslationConfig:
    model_path: str = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    batch_size: int = 10
    max_tokens: int = 2048
    temperature: float = 0.0
    max_retries: int = 1
    retry_delay: float = 1.0
    context_window: int = 3
