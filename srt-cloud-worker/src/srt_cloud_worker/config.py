"""Runtime configuration for translation."""

from dataclasses import dataclass
from pathlib import Path

from pkg_translator.api import TranslationConfig as BaseTranslationConfig
from pkg_translator.api import load_local_env as _load_local_env

_PROJECT_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class TranslationConfig(BaseTranslationConfig):
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    batch_size: int = 100
    max_tokens: int = 8192
    request_timeout: float = 60.0


def load_local_env(path: str | Path | None = None) -> None:
    """Load key/value pairs from the worker's local .env file if present."""
    _load_local_env(path, default_dir=_PROJECT_DIR)
