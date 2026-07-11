"""Integration tests for /api/jobs* — POST, GET list, GET one, download.

Drives the real FastAPI app through TestClient (lifespan runs Alembic +
seeds dev user + starts worker_loop). The streaming worker call is
patched out — these tests verify the persistence + queue wiring, not
worker I/O (covered by slice-2 integration checkpoints against a live
worker).
"""

from __future__ import annotations

import time
from typing import Any

import pytest

CUE_EN = {"index": 1, "start": "00:00:01,000", "end": "00:00:02,000", "text": "Hello"}


def _wait_for_status(
    client: Any, job_id: str, target: set[str], timeout: float = 5.0
) -> dict[str, Any]:
    """Poll GET /api/jobs/{id} until status enters ``target`` or timeout."""
    deadline = time.time() + timeout
    body: dict[str, Any] = {}
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body.get("status") in target:
            return body
        time.sleep(0.05)
    return body


def test_create_job_returns_202_and_inserts_pending(client: Any, fake_worker: Any) -> None:
    client.app.state.job_ctx.worker_client = fake_worker  # type: ignore[method-assign]
    resp = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr", "de"],
            "worker": "mlx",
            "filename": "episode-01.srt",
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body and len(body["job_id"]) > 0

    # The job row exists in pending (race-free: GET immediately).
    status = client.get(f"/api/jobs/{body['job_id']}").json()
    # The worker_loop may already have started processing — accept either.
    assert status["status"] in {"pending", "processing", "done"}
    assert status["filename"] == "episode-01.srt"


@pytest.mark.parametrize(
    "filename",
    ["a" * 256, "bad\nname.srt", "bad\x00name.srt", "folder/name.srt", "folder\\name.srt", ".."],
)
def test_create_rejects_unsafe_filename(client: Any, filename: str) -> None:
    response = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "mlx",
            "filename": filename,
        },
    )
    assert response.status_code == 422


def test_create_treats_empty_filename_as_null(client: Any, fake_worker: Any) -> None:
    client.app.state.job_ctx.worker_client = fake_worker  # type: ignore[method-assign]
    response = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "mlx",
            "filename": "   ",
        },
    )
    assert response.status_code == 202
    detail = client.get(f"/api/jobs/{response.json()['job_id']}").json()
    assert detail["filename"] is None


def test_full_flow_processes_to_done_with_download(client: Any, patched_worker: Any) -> None:
    resp = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "mlx",
        },
    )
    job_id = resp.json()["job_id"]

    body = _wait_for_status(client, job_id, {"done", "failed"})
    assert body["status"] == "done", f"error: {body.get('error')}"
    assert body["progress"] == 1.0
    assert body["tgt_langs"] == ["fr"]
    assert body["created_at"]
    assert body["started_at"]
    assert body["finished_at"]
    assert body["attempts"] == 1
    assert body["error_kind"] is None
    assert body["dropped_by_target"] == {"fr": 0}

    # Result shape is the slice-3 contract: {lang, download_url}, no inline srt.
    results = body["results"]
    assert results == [{"lang": "fr", "download_url": f"/api/jobs/{job_id}/download?lang=fr"}]

    # Download streams the file.
    dl = client.get(results[0]["download_url"])
    assert dl.status_code == 200
    assert b"[fr] Hello" in dl.content
    assert 'attachment; filename="' in dl.headers.get("content-disposition", "")

    # One call recorded against the fake worker.
    assert len(patched_worker.calls) == 1
    call = patched_worker.calls[0]
    assert call["source_lang"] == "en"
    assert call["targets"] == ["fr"]
    assert call["segments"] == [{"id": 1, "en": "Hello"}]


def test_list_jobs_returns_dev_user_history(client: Any, patched_worker: Any) -> None:
    # Two jobs, different targets.
    for tgt in ["fr", "de"]:
        resp = client.post(
            "/api/jobs",
            json={
                "cues": [CUE_EN],
                "source_lang": "en",
                "targets": [tgt],
                "worker": "mlx",
            },
        )
        assert resp.status_code == 202

    _wait_for_status(client, resp.json()["job_id"], {"done", "failed"})

    body = client.get("/api/jobs").json()
    jobs = body["jobs"]
    assert len(jobs) == 2
    # Newest-first ordering.
    assert jobs[0]["created_at"] >= jobs[1]["created_at"]
    # Each list item carries the documented summary fields.
    for j in jobs:
        assert {"id", "status", "worker", "src_lang", "tgt_langs", "progress", "created_at"} <= set(
            j
        )


def test_get_unknown_job_404(client: Any) -> None:
    resp = client.get("/api/jobs/does-not-exist")
    assert resp.status_code == 404


def test_create_rejects_unknown_worker(client: Any) -> None:
    resp = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "ghost",
        },
    )
    assert resp.status_code == 404


def test_create_rejects_source_only_targets(client: Any) -> None:
    resp = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["en"],
            "worker": "mlx",
        },
    )
    assert resp.status_code == 400


def test_create_rejects_malformed_cue(client: Any) -> None:
    resp = client.post(
        "/api/jobs",
        json={
            "cues": [{"index": 1, "start": "x"}],  # missing end/text
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "mlx",
        },
    )
    assert resp.status_code == 400


def test_download_404_for_unknown_lang(client: Any, patched_worker: Any) -> None:
    resp = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "mlx",
        },
    )
    job_id = resp.json()["job_id"]
    _wait_for_status(client, job_id, {"done", "failed"})

    dl = client.get(f"/api/jobs/{job_id}/download?lang=de")
    assert dl.status_code == 404


def test_download_conflict_before_done(client: Any, fake_worker: Any) -> None:
    # Use a worker client that hangs so the job stays in processing.
    class _HangingClient:
        async def __call__(self, *args: Any, **kwargs: Any) -> Any:
            import asyncio as _a

            await _a.sleep(30)

    client.app.state.job_ctx.worker_client = _HangingClient()  # type: ignore[method-assign]
    resp = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "mlx",
        },
    )
    job_id = resp.json()["job_id"]
    _wait_for_status(client, job_id, {"processing"})

    dl = client.get(f"/api/jobs/{job_id}/download?lang=fr")
    assert dl.status_code == 409


def test_failed_job_records_error(client: Any, fake_worker: Any) -> None:
    from pkg_job_orch.api import WorkerStreamError

    class _FailingClient:
        async def __call__(self, *args: Any, **kwargs: Any) -> Any:
            raise WorkerStreamError("boom")

    client.app.state.job_ctx.worker_client = _FailingClient()  # type: ignore[method-assign]
    resp = client.post(
        "/api/jobs",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "mlx",
        },
    )
    job_id = resp.json()["job_id"]
    body = _wait_for_status(client, job_id, {"done", "failed"})
    assert body["status"] == "failed"
    assert "boom" in body["error"]
    assert body["error_kind"] == "worker_stream"
    assert body["attempts"] == 1
    assert body["started_at"] is not None
    assert "dropped_by_target" not in body
    # No results on a failed job.
    assert "results" not in body


if __name__ == "__main__":
    pytest.main([__file__])
