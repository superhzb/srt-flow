"""Tests for /api/translate and /api/translate/{job_id}.

The streaming worker HTTP call is patched out — these tests verify job
lifecycle wiring and request validation, not worker I/O (covered by the
slice-2 integration checkpoint against a live worker).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from srt_backend.app import api

client = TestClient(api)

CUE_EN = {"index": 1, "start": "00:00:01,000", "end": "00:00:02,000", "text": "Hello"}


def _patch_run_translation(
    monkeypatch: pytest.MonkeyPatch,
    fake: Callable[..., Awaitable[None]],
) -> None:
    monkeypatch.setattr("srt_backend.routes_translate.run_translation", fake)


async def _noop_fake(**_kwargs: object) -> None:
    return None


def test_start_translate_returns_job_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run_translation(monkeypatch, _noop_fake)

    resp = client.post(
        "/api/translate",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr", "zh"],
            "worker": "mlx",
        },
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "job_id" in body and len(body["job_id"]) > 0


def test_translate_status_transitions_when_fake_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from srt_backend.jobs import Job

    async def fake(**kwargs: object) -> None:
        job = kwargs["job"]
        assert isinstance(job, Job)
        job.status = "done"
        job.progress = 1.0
        job.results = [
            {"lang": "fr", "srt": "1\n00:00:01,000 --> 00:00:02,000\nBonjour\n"}
        ]

    _patch_run_translation(monkeypatch, fake)

    # Force the fake to run inline by awaiting it within the route's create_task
    # via the global event loop used by TestClient.
    with client:
        resp = client.post(
            "/api/translate",
            json={
                "cues": [CUE_EN],
                "source_lang": "en",
                "targets": ["fr"],
                "worker": "mlx",
            },
        )
        job_id = resp.json()["job_id"]
        # The create_task coroutine runs after the response is sent; loop until
        # status stabilises.
        import time

        deadline = time.time() + 2.0
        body: dict[str, Any] = {}
        while time.time() < deadline:
            body = client.get(f"/api/translate/{job_id}").json()
            if body["status"] in {"done", "failed"}:
                break
            time.sleep(0.02)

    assert body["status"] == "done"
    assert body["progress"] == 1.0
    assert body["results"] == [
        {"lang": "fr", "srt": "1\n00:00:01,000 --> 00:00:02,000\nBonjour\n"}
    ]


def test_translate_rejects_unknown_worker() -> None:
    resp = client.post(
        "/api/translate",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "ghost",
        },
    )
    assert resp.status_code == 404


def test_translate_rejects_source_only_targets() -> None:
    resp = client.post(
        "/api/translate",
        json={
            "cues": [CUE_EN],
            "source_lang": "en",
            "targets": ["en"],
            "worker": "mlx",
        },
    )
    assert resp.status_code == 400


def test_translate_status_404_on_unknown_job() -> None:
    resp = client.get("/api/translate/does-not-exist")
    assert resp.status_code == 404


def test_translate_rejects_malformed_cue() -> None:
    resp = client.post(
        "/api/translate",
        json={
            "cues": [{"index": 1, "start": "x"}],  # missing end/text
            "source_lang": "en",
            "targets": ["fr"],
            "worker": "mlx",
        },
    )
    assert resp.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__])
