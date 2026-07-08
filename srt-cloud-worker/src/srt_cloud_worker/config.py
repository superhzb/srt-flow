"""Runtime configuration for translation."""

import os
from dataclasses import dataclass
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _PACKAGE_DIR.parents[1]


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


def load_local_env(path: str | Path | None = None) -> None:
    """Load key/value pairs from the worker's local .env file if present."""
    env_path = Path(path) if path is not None else _PROJECT_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _parse_env_value(value)


def _parse_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
