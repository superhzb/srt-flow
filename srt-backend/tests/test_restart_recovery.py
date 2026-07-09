"""Restart-recovery tests: jobs survive backend kill + restart.

Drives the real lifespan twice against the same DATABASE_URL/STORAGE_ROOT
so the second startup runs the recover-scan + replay against the first
session's leftover rows.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

CUE_EN = {"index": 1, "start": "00:00:01,000", "end": "00:00:02,000", "text": "Hello"}


def _wait_for_status(
    client: Any, job_id: str, target: set[str], timeout: float = 5.0
) -> dict[str, Any]:
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body.get("status") in target:
            return body
        time.sleep(0.05)
    return body


def test_processing_job_resumes_after_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kill mid-flight → restart → job reaches done."""
    db_dir = Path(tempfile.mkdtemp(prefix="srt-recover-db-"))
    storage_dir = Path(tempfile.mkdtemp(prefix="srt-recover-storage-"))
    db_url = f"sqlite:///{db_dir / 'test.sqlite'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("STORAGE_ROOT", str(storage_dir))
    monkeypatch.setenv("WORKERS", "mlx=http://localhost:5732")
    try:
        from fastapi.testclient import TestClient
        from srt_backend.app import api

        # Session 1: enqueue a job that hangs in processing forever.
        class _HangingClient:
            async def __call__(self, *args: Any, **kwargs: Any) -> Any:
                import asyncio as _a

                await _a.sleep(60)

        with TestClient(api) as c:
            c.app.state.job_ctx.worker_client = _HangingClient()  # type: ignore[method-assign]
            resp = c.post(
                "/api/jobs",
                json={
                    "cues": [CUE_EN],
                    "source_lang": "en",
                    "targets": ["fr"],
                    "worker": "mlx",
                },
            )
            job_id = resp.json()["job_id"]
            _wait_for_status(c, job_id, {"processing"})

        # Session 1 ended (lifespan shutdown). The job is left in processing.
        # Session 2: restart with a real (fake) worker client — recover flips
        # processing → pending and re-enqueues; worker_loop completes it.
        # Patch default_worker_client BEFORE the lifespan constructs the
        # JobContext so the loop uses the fake from the very first iteration.
        class _OkClient:
            async def __call__(
                self,
                base_url: str,
                source_lang: str,
                targets: list[str],
                segments: list[dict[str, Any]],
                on_progress: Any,
            ) -> dict[str, Any]:
                if on_progress is not None:
                    on_progress(1.0)
                return {
                    "source_lang": source_lang,
                    "targets": targets,
                    "segments": [
                        {"id": seg["id"],
                         **{t: f"[{t}] {seg[source_lang]}" for t in targets}}
                        for seg in segments
                    ],
                }

        import pkg_job_orch.orchestration as orch

        monkeypatch.setattr(orch, "default_worker_client", _OkClient())

        with TestClient(api) as c:
            body = _wait_for_status(c, job_id, {"done", "failed"}, timeout=10.0)
            assert body["status"] == "done", f"error: {body.get('error')}"
            # Output file landed on disk during the resumed run.
            dl = c.get(f"/api/jobs/{job_id}/download?lang=fr")
            assert dl.status_code == 200
            assert b"[fr] Hello" in dl.content
    finally:
        shutil.rmtree(db_dir, ignore_errors=True)
        shutil.rmtree(storage_dir, ignore_errors=True)


def test_done_job_survives_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    """A completed job is still done + downloadable after restart."""
    db_dir = Path(tempfile.mkdtemp(prefix="srt-done-db-"))
    storage_dir = Path(tempfile.mkdtemp(prefix="srt-done-storage-"))
    db_url = f"sqlite:///{db_dir / 'test.sqlite'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("STORAGE_ROOT", str(storage_dir))
    monkeypatch.setenv("WORKERS", "mlx=http://localhost:5732")
    try:
        from fastapi.testclient import TestClient
        from srt_backend.app import api

        class _OkClient:
            async def __call__(
                self,
                base_url: str,
                source_lang: str,
                targets: list[str],
                segments: list[dict[str, Any]],
                on_progress: Any,
            ) -> dict[str, Any]:
                return {
                    "source_lang": source_lang,
                    "targets": targets,
                    "segments": [
                        {"id": seg["id"],
                         **{t: f"[{t}] {seg[source_lang]}" for t in targets}}
                        for seg in segments
                    ],
                }

        with TestClient(api) as c:
            c.app.state.job_ctx.worker_client = _OkClient()  # type: ignore[method-assign]
            resp = c.post(
                "/api/jobs",
                json={
                    "cues": [CUE_EN],
                    "source_lang": "en",
                    "targets": ["de"],
                    "worker": "mlx",
                },
            )
            job_id = resp.json()["job_id"]
            body = _wait_for_status(c, job_id, {"done"})
            assert body["status"] == "done"

        # Restart: the done job is still done and downloadable.
        with TestClient(api) as c:
            status = c.get(f"/api/jobs/{job_id}").json()
            assert status["status"] == "done"
            assert status["progress"] == 1.0
            dl = c.get(f"/api/jobs/{job_id}/download?lang=de")
            assert dl.status_code == 200
            assert b"[de] Hello" in dl.content

        _ = os  # silence ruff if env changes; reserved for future use
    finally:
        shutil.rmtree(db_dir, ignore_errors=True)
        shutil.rmtree(storage_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
