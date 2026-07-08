"""Runtime configuration for translation."""

from dataclasses import dataclass
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class TranslationConfig:
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "DEEPSEEK_API_KEY"
    template_path: str = str(_PACKAGE_DIR / "template.txt")
    languages_path: str = str(_PACKAGE_DIR / "languages.yaml")
    batch_size: int = 100
    max_tokens: int = 8192
    temperature: float = 0.0
    max_retries: int = 1
    retry_delay: float = 1.0
    context_window: int = 3
    request_timeout: float = 60.0
