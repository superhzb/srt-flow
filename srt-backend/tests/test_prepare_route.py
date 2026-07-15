"""Tests for /api/srt/prepare route."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from srt_backend.app import api

client = TestClient(api)

EN_SRT = b"""1
00:00:01,000 --> 00:00:04,000
It takes real strength to make it all the way to the end.

2
00:00:04,000 --> 00:00:07,000
You have to be brave enough to face what comes next.
"""

TRADITIONAL_SRT = b"""1
00:00:01,000 --> 00:00:02,000
\xe8\x80\x8c\xe4\xb8\x94\xe8\xa6\x81\xe8\xb5\xb0\xe5\x88\xb0\xe6\x9c\x80\xe5\xbe\x8c\xef\xbc\x8c\xe7\x9c\x9f\xe7\x9a\x84\xe9\x9c\x80\xe8\xa6\x81\xe5\xbe\x88\xe5\xbc\xb7
"""


def _files(body: bytes, name: str = "sample.srt") -> dict[str, tuple[str, bytes]]:
    return {"file": (name, body)}


def test_prepare_returns_cues_and_detected_english() -> None:
    resp = client.post("/api/srt/prepare", files=_files(EN_SRT))
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["cues"][0]["index"] == 1
    assert body["detected_lang"] == "en"
    assert body["confidence"] >= 0.5


def test_prepare_detects_traditional_chinese() -> None:
    resp = client.post("/api/srt/prepare", files=_files(TRADITIONAL_SRT))
    assert resp.status_code == 200
    assert resp.json()["detected_lang"] == "zh-TW"


def test_prepare_rejects_wrong_extension() -> None:
    resp = client.post("/api/srt/prepare", files=_files(EN_SRT, name="x.txt"))
    assert resp.status_code == 400


def test_prepare_rejects_unparseable() -> None:
    resp = client.post("/api/srt/prepare", files=_files(b"1\nnot a timespan\nHi\n"))
    assert resp.status_code == 400


def test_prepare_rate_limit_and_forwarded_client_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PREPARE_RATE_LIMIT", "2")
    monkeypatch.setenv("PREPARE_RATE_WINDOW_SECONDS", "600")
    headers = {"x-forwarded-for": "198.51.100.10"}
    assert client.post("/api/srt/prepare", files=_files(EN_SRT), headers=headers).status_code == 200
    assert client.post("/api/srt/prepare", files=_files(EN_SRT), headers=headers).status_code == 200
    limited = client.post("/api/srt/prepare", files=_files(EN_SRT), headers=headers)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0

    other_client = {"x-forwarded-for": "198.51.100.11"}
    assert (
        client.post("/api/srt/prepare", files=_files(EN_SRT), headers=other_client).status_code
        == 200
    )


if __name__ == "__main__":
    pytest.main([__file__])
