"""Test isolation for srt-backend integration tests.

Each test gets a fresh tmp DATABASE_URL + STORAGE_ROOT. The TestClient
drives the real lifespan (Alembic + dev-user seed + recover + worker_loop
start) so endpoints see a fully booted app.

The worker_loop is real but idle by default — tests that POST a job
patch ``app.state.job_ctx.worker_client`` to a fake so the loop processes
the job deterministically without hitting any real worker HTTP.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _reset_billing_settings_cache() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Clear the cached billing settings so each test re-reads its own env."""
    from pkg_billing.api import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def temp_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    """Set isolated DATABASE_URL + STORAGE_ROOT for one test.

    Forces a fresh engine + on-disk layout per test. The lifespan reads
    these on entry (run_migrations / LocalStorage / recover), so they
    must be set before ``TestClient(api).__enter__``.
    """
    db_dir = Path(tempfile.mkdtemp(prefix="srt-test-db-"))
    storage_dir = Path(tempfile.mkdtemp(prefix="srt-test-storage-"))
    db_url = f"sqlite:///{db_dir / 'test.sqlite'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("STORAGE_ROOT", str(storage_dir))
    # Pin dev auth so these integration tests are hermetic: the app's
    # load_dotenv(".env") must not decide auth mode from a developer's local
    # .env (which may be AUTH_MODE=google). load_dotenv won't override these.
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    # Default LLM_BACKENDS enables cloud/mlx; tests resolve worker ids via this.
    monkeypatch.setenv("LLM_BACKENDS", "mlx,cloud")
    yield {"DATABASE_URL": db_url, "STORAGE_ROOT": str(storage_dir)}
    shutil.rmtree(db_dir, ignore_errors=True)
    shutil.rmtree(storage_dir, ignore_errors=True)


class FakeWorkerClient:
    """Deterministic stand-in for the streaming worker client.

    Records every call and lets a test set the outcome or raise. Default
    behaviour: emit one progress tick and return one translated segment
    per target by prefixing the source text with ``[<lang>]``.
    """

    def __init__(
        self,
        outcome: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
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
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "base_url": base_url,
                "source_lang": source_lang,
                "targets": list(targets),
                "segments": list(segments),
            }
        )
        if on_progress is not None:
            on_progress(0.5)
        if self._error is not None:
            raise self._error
        if self._outcome is not None:
            return self._outcome
        return {
            "source_lang": source_lang,
            "targets": targets,
            "segments": [
                {"id": seg["id"], **{t: f"[{t}] {seg[source_lang]}" for t in targets}}
                for seg in segments
            ],
        }


@pytest.fixture
def fake_worker() -> FakeWorkerClient:
    return FakeWorkerClient()


@pytest.fixture
def client(temp_env: dict[str, str]) -> Iterator[Any]:
    """TestClient with lifespan run + worker_loop patched to a noop client.

    The worker_loop starts but immediately sits idle (no jobs enqueued by
    default). Tests that POST a job should swap the worker_client before
    or after the POST — see ``patched_worker`` fixture.
    """
    # Imported lazily so module import doesn't trigger env reads.
    from fastapi.testclient import TestClient
    from srt_backend.app import api

    with TestClient(api) as c:
        yield c


@pytest.fixture
def patched_worker(client: Any, fake_worker: FakeWorkerClient) -> FakeWorkerClient:
    """Swap the running app's worker_client for ``fake_worker``.

    The lifespan has already started worker_loop with the default
    ``default_worker_client``; we replace it in place so the loop picks
    up the fake on its next job.
    """
    ctx = client.app.state.job_ctx
    ctx.worker_client = fake_worker  # type: ignore[method-assign]
    return fake_worker
