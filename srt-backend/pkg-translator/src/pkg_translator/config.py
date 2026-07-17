"""Runtime configuration for translation."""

import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path


def package_resource_path(name: str) -> str:
    """Return a filesystem path for package data without assuming source layout."""
    return str(resources.files("pkg_translator").joinpath(name))


@dataclass(frozen=True)
class TranslationConfig:
    template_path: str = field(default_factory=lambda: package_resource_path("template.txt"))
    languages_path: str = field(default_factory=lambda: package_resource_path("languages.yaml"))
    batch_size: int = 10
    max_tokens: int = 2048
    temperature: float = 0.0
    max_retries: int = 1
    retry_delay: float = 1.0
    context_window: int = 3


def load_local_env(path: str | Path | None = None, *, default_dir: Path | None = None) -> None:
    """Load key/value pairs from a local .env file if present."""
    env_path = Path(path) if path is not None else (default_dir or Path.cwd()) / ".env"
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
