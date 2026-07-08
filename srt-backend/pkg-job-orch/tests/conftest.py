"""Shared fixtures for pkg_job_orch tests.

Every test gets an isolated in-memory SQLite + temp STORAGE_ROOT.
``init_schema`` is used (not Alembic) for unit-test speed; the
migrations themselves are exercised in ``test_models.py`` via run_migrations.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from pkg_file_upload.api import LocalStorage

from pkg_job_orch.api import DEV_USER_ID, JobContext, NullNotifier, reset_engine
from pkg_job_orch.db import init_schema


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[str, None, None]:
    """Isolated in-memory SQLite — one per test, no on-disk cleanup."""
    url = "sqlite://"
    monkeypatch.setenv("DATABASE_URL", url)
    reset_engine()
    init_schema(url)
    yield url
    reset_engine()


@pytest.fixture
def temp_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalStorage:
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    monkeypatch.setenv("STORAGE_ROOT", str(storage_root))
    return LocalStorage(storage_root)


@pytest.fixture
def job_ctx(temp_storage: LocalStorage) -> JobContext:
    """A JobContext wired for real tests; tests patch ``worker_client``."""
    import asyncio

    return JobContext(
        queue=asyncio.Queue(),
        storage=temp_storage,
        dev_user_id=DEV_USER_ID,
        notifier=NullNotifier(),
    )


class FakeWorkerClient:
    """Records calls + lets the test set the outcome. Defaults to success."""

    def __init__(self, outcome: Any | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._outcome = outcome
        self._error = error

    async def __call__(
        self,
        base_url: str,
        source_lang: str,
        targets: list[str],
        segments: list[dict[str, Any]],
        on_progress: Any,
    ) -> Any:
        self.calls.append(
            {
                "base_url": base_url,
                "source_lang": source_lang,
                "targets": list(targets),
                "segments": list(segments),
                "on_progress": on_progress,
            }
        )
        if on_progress is not None:
            on_progress(0.5)
        if self._error is not None:
            raise self._error
        if self._outcome is None:
            # Default synthetic outcome: one translated segment per target.
            return {
                "source_lang": source_lang,
                "targets": targets,
                "segments": [
                    {"id": seg["id"], **{t: f"[{t}] {seg[source_lang]}" for t in targets}}
                    for seg in segments
                ],
            }
        return self._outcome


@pytest.fixture
def fake_worker_client() -> FakeWorkerClient:
    return FakeWorkerClient()
