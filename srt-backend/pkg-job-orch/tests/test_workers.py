"""Tests for the in-process worker registry (Phase B).

``workers_env``/``worker_backend_config``/``probe_workers``/``fetch_languages``
now resolve against ``pkg_llm_backend.load_backends()`` (env ``LLM_BACKENDS``)
instead of proxying HTTP to standalone worker services.
"""

from __future__ import annotations

import pytest
from pkg_job_orch.workers import (
    WorkerInfo,
    WorkerResolutionError,
    fetch_languages,
    probe_workers,
    worker_backend_config,
    worker_base_url,
    workers_env,
)
from pkg_llm_backend.api import Backend, LLMBackendConfig


def test_workers_env_lists_enabled_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "cloud,mlx")

    infos = workers_env()

    assert [i.id for i in infos] == ["cloud", "mlx"]
    assert infos[0].base_url == "https://api.deepseek.com"


def test_workers_env_rejects_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "ghost")

    with pytest.raises(WorkerResolutionError, match="unknown"):
        workers_env()


def test_worker_backend_config_resolves_and_unknown_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    config = worker_backend_config("mlx")
    assert config.model == "local-chat"

    with pytest.raises(WorkerResolutionError, match="unknown worker id"):
        worker_backend_config("cloud")


def test_worker_base_url_resolves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")
    monkeypatch.setenv("MLX_PLATFORM_BASE_URL", "http://127.0.0.1:5900/v1")

    assert worker_base_url("mlx") == "http://127.0.0.1:5900/v1"


def test_worker_label_falls_back_to_title_case() -> None:
    assert WorkerInfo(id="cloud", base_url="u").label == "Cloud (DeepSeek)"
    assert WorkerInfo(id="custom", base_url="u").label == "Custom"


async def test_probe_workers_reports_health_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "cloud,mlx")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def fake_ensure_model_available(_self: Backend, config: LLMBackendConfig) -> None:
        del config
        raise RuntimeError("gateway unreachable")

    monkeypatch.setattr(Backend, "ensure_model_available", fake_ensure_model_available)

    infos = workers_env()
    statuses = await probe_workers(infos)

    assert [(s.id, s.healthy) for s in statuses] == [("cloud", False), ("mlx", False)]


async def test_probe_workers_reports_healthy_when_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "cloud")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    [status] = await probe_workers(workers_env())

    assert status.id == "cloud"
    assert status.healthy is True


async def test_fetch_languages_returns_catalog_for_known_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    result = await fetch_languages("mlx")

    assert "languages" in result
    assert isinstance(result["languages"], list)
    assert result["languages"]


async def test_fetch_languages_raises_for_unknown_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    with pytest.raises(WorkerResolutionError, match="unknown worker id"):
        await fetch_languages("cloud")
