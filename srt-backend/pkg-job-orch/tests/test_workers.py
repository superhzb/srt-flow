"""Tests for the worker registry + HTTP helpers (Phase 6 #28).

``probe_workers``, ``fetch_languages``, and the ``WORKERS`` parser were
previously untested. The HTTP helpers are driven via ``httpx.MockTransport``
(no socket).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pkg_job_orch import workers
from pkg_job_orch.workers import (
    WorkerInfo,
    WorkerResolutionError,
    fetch_languages,
    probe_workers,
    worker_base_url,
    workers_env,
)


def _patch_httpx(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    real_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def factory(*_args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs.pop("timeout", None)
        kwargs["transport"] = transport
        return real_async_client(**kwargs)

    monkeypatch.setattr(workers.httpx, "AsyncClient", factory)


def test_workers_env_parses_and_strips() -> None:
    infos = workers_env(" cloud = http://localhost:5733 , mlx=http://localhost:5732 , ")

    assert infos == [
        WorkerInfo(id="cloud", base_url="http://localhost:5733"),
        WorkerInfo(id="mlx", base_url="http://localhost:5732"),
    ]
    # Trailing slash on a base_url is normalized away.
    assert workers_env("x=http://h:1/")[0].base_url == "http://h:1"


def test_workers_env_rejects_malformed_entry() -> None:
    with pytest.raises(WorkerResolutionError, match="expected 'id=url'"):
        workers_env("not-a-pair")


def test_workers_env_rejects_empty_id_or_url() -> None:
    with pytest.raises(WorkerResolutionError, match="empty id or url"):
        workers_env("=http://localhost")


def test_worker_base_url_resolves_and_unknown_raises() -> None:
    raw = "cloud=http://h:1,mlx=http://h:2"
    assert worker_base_url("mlx", raw) == "http://h:2"

    with pytest.raises(WorkerResolutionError, match="unknown worker id"):
        worker_base_url("nope", raw)


def test_worker_label_falls_back_to_title_case() -> None:
    assert WorkerInfo(id="cloud", base_url="u").label == "Cloud (DeepSeek)"
    assert WorkerInfo(id="custom", base_url="u").label == "Custom"


async def test_probe_workers_reports_health_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infos = [
        WorkerInfo(id="up", base_url="http://up"),
        WorkerInfo(id="down", base_url="http://down"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "up":
            return httpx.Response(200)
        raise httpx.ConnectError("connection refused")  # type: ignore[call-arg]

    _patch_httpx(monkeypatch, handler)

    statuses = await probe_workers(infos)

    assert [(s.id, s.healthy) for s in statuses] == [("up", True), ("down", False)]


async def test_probe_workers_treats_non_200_as_unhealthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infos = [WorkerInfo(id="w", base_url="http://w")]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    _patch_httpx(monkeypatch, handler)

    [status] = await probe_workers(infos)
    assert status.healthy is False


async def test_fetch_languages_returns_json_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"languages": [{"code": "es", "name": "Spanish"}]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    _patch_httpx(monkeypatch, handler)

    assert await fetch_languages("http://w") == payload


async def test_fetch_languages_raises_on_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    _patch_httpx(monkeypatch, handler)

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_languages("http://w")
