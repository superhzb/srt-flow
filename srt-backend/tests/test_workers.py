"""Tests for worker registry resolution via the public pkg_job_orch API (no network)."""

from __future__ import annotations

import pytest
from pkg_job_orch.api import (
    WorkerResolutionError,
    worker_backend_config,
    worker_base_url,
    workers_env,
)


def test_workers_env_lists_enabled_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "cloud,mlx")

    infos = workers_env()

    assert [i.id for i in infos] == ["cloud", "mlx"]
    assert infos[0].base_url == "https://api.deepseek.com"


def test_workers_env_label_known_vs_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "cloud,mlx")

    infos = workers_env()

    labels = {i.id: i.label for i in infos}
    assert labels["cloud"] == "Cloud (DeepSeek)"
    assert labels["mlx"] == "Local MLX"


def test_workers_env_rejects_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "ghost")

    with pytest.raises(WorkerResolutionError):
        workers_env()


def test_worker_base_url_resolves_known_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")
    monkeypatch.setenv("MLX_PLATFORM_BASE_URL", "http://127.0.0.1:5900/v1")

    assert worker_base_url("mlx") == "http://127.0.0.1:5900/v1"


def test_worker_base_url_raises_on_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    with pytest.raises(WorkerResolutionError):
        worker_base_url("ghost")


def test_worker_backend_config_raises_on_unknown_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BACKENDS", "mlx")

    with pytest.raises(WorkerResolutionError):
        worker_backend_config("ghost")
