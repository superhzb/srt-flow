"""Runtime configuration for translation."""

from dataclasses import dataclass
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class TranslationConfig:
    model_path: str = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    template_path: str = str(_PACKAGE_DIR / "template.txt")
    languages_path: str = str(_PACKAGE_DIR / "languages.yaml")
    batch_size: int = 10
    max_tokens: int = 2048
    temperature: float = 0.0
    max_retries: int = 1
    retry_delay: float = 1.0
    context_window: int = 3
