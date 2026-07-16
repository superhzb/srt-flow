"""Job-orchestration configuration (Phase 3 #12 — converged on pydantic-settings).

Env is read through one ``JobOrchSettings`` model instead of scattered inline
``os.environ.get`` calls. The ``DEFAULT_*`` constants live here (single source)
and are re-exported by ``db``/``workers``/``orchestration`` for back-compat.

``load_settings`` returns a fresh instance per call (no cache): these reads are
cheap and low-frequency, and a fresh read lets tests ``monkeypatch.setenv``
and immediately observe the change without a cache-reset hook.
"""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "DEFAULT_DATABASE_URL",
    "DEFAULT_DEV_USER_EMAIL",
    "DEFAULT_WORKERS",
    "JobOrchSettings",
    "load_settings",
]

DEFAULT_DATABASE_URL = "sqlite:///./.data/dev/db.sqlite"
DEFAULT_WORKERS = "mlx=http://localhost:5732,cloud=http://localhost:5733"
DEFAULT_DEV_USER_EMAIL = "dev@local"


class JobOrchSettings(BaseSettings):
    """Runtime settings loaded from env (DATABASE_URL, WORKERS, DEV_USER_*)."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = DEFAULT_DATABASE_URL
    workers: str = DEFAULT_WORKERS
    dev_user_email: str = DEFAULT_DEV_USER_EMAIL
    dev_user_tier: str = "paid"

    @field_validator("dev_user_tier")
    @classmethod
    def _validate_dev_user_tier(cls, value: str) -> str:
        if value not in {"free", "paid"}:
            msg = "DEV_USER_TIER must be 'free' or 'paid'"
            raise ValueError(msg)
        return value


def load_settings() -> JobOrchSettings:
    """Load job-orch env settings (fresh read each call — see module docstring)."""
    return JobOrchSettings()
