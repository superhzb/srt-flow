"""Tests for the SRT parse route."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from srt_backend.app import api

client = TestClient(api)

SIMPLE_SRT = b"""1
00:00:01,000 --> 00:00:04,074
Hello world

2
00:00:04,074 --> 00:00:07,048
Second cue
spans two lines
"""


def _files(body: bytes = SIMPLE_SRT, name: str = "sample.srt") -> dict[str, tuple[str, bytes]]:
    return {"file": (name, body)}


def test_parse_ok() -> None:
    resp = client.post("/api/srt/parse", files=_files())
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["cues"][0] == {
        "index": 1,
        "start": "00:00:01,000",
        "end": "00:00:04,074",
        "text": "Hello world",
    }
    assert body["cues"][1]["text"] == "Second cue\nspans two lines"


def test_parse_utf8_bytes_preserved() -> None:
    body = b"1\n00:00:01,000 --> 00:00:02,000\n\xc3\x9cn\xc3\xafcoded\xe2\x80\x94emdash\n\n"
    resp = client.post("/api/srt/parse", files=_files(body=body))
    assert resp.status_code == 200
    assert resp.json()["cues"][0]["text"] == "Ünïcoded—emdash"


def test_parse_wrong_extension_400() -> None:
    resp = client.post("/api/srt/parse", files=_files(name="x.txt"))
    assert resp.status_code == 400


def test_parse_empty_body_400() -> None:
    resp = client.post("/api/srt/parse", files=_files(body=b""))
    assert resp.status_code == 400


def test_parse_malformed_400() -> None:
    resp = client.post(
        "/api/srt/parse",
        files=_files(body=b"1\nnot a timespan\nHi\n"),
    )
    assert resp.status_code == 400
    assert "timespan" in resp.json()["detail"]


def test_parse_invalid_utf8_400() -> None:
    resp = client.post(
        "/api/srt/parse",
        files=_files(body=b"1\n\xff\xfe bad bytes\nHi\n"),
    )
    assert resp.status_code == 400


def test_parse_file_too_large_400() -> None:
    big = b"0" * (4 * 1024 * 1024 + 1)
    resp = client.post("/api/srt/parse", files=_files(body=big))
    assert resp.status_code == 400


if __name__ == "__main__":
    pytest.main([__file__])
