"""Tests for worker env parsing and resolution (no network)."""

from __future__ import annotations

import pytest

from srt_backend.workers import (
    WorkerResolutionError,
    worker_base_url,
    workers_env,
)


def test_workers_env_parses_id_url_pairs() -> None:
    infos = workers_env("cloud=http://localhost:5733, mlx=http://localhost:5732")
    assert [i.id for i in infos] == ["cloud", "mlx"]
    assert infos[0].base_url == "http://localhost:5733"
    assert infos[1].base_url == "http://localhost:5732"


def test_workers_env_strips_trailing_slash() -> None:
    infos = workers_env("cloud=http://localhost:5733/")
    assert infos[0].base_url == "http://localhost:5733"


def test_workers_env_label_known_vs_unknown() -> None:
    infos = workers_env("cloud=http://x,mlx=http://y,weird=http://z")
    labels = {i.id: i.label for i in infos}
    assert labels["cloud"] == "Cloud (DeepSeek)"
    assert labels["mlx"] == "Local MLX"
    assert labels["weird"] == "Weird"  # title-case fallback


def test_workers_env_skips_empty_tokens() -> None:
    infos = workers_env("cloud=http://x,, ,mlx=http://y")
    assert [i.id for i in infos] == ["cloud", "mlx"]


def test_workers_env_rejects_missing_equals() -> None:
    with pytest.raises(WorkerResolutionError):
        workers_env("cloud-not-a-url")


def test_workers_env_rejects_empty_id_or_url() -> None:
    with pytest.raises(WorkerResolutionError):
        workers_env("=http://x")
    with pytest.raises(WorkerResolutionError):
        workers_env("cloud=")


def test_worker_base_url_resolves_known_id() -> None:
    url = worker_base_url("mlx", raw="mlx=http://localhost:5732")
    assert url == "http://localhost:5732"


def test_worker_base_url_raises_on_unknown_id() -> None:
    with pytest.raises(WorkerResolutionError):
        worker_base_url("ghost", raw="mlx=http://localhost:5732")
