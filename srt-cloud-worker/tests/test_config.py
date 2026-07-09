import os
from pathlib import Path

import pytest
from srt_cloud_worker.config import load_local_env


def test_load_local_env_sets_missing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                'DEEPSEEK_API_KEY="test-key"',
                "export WORKER_PORT=5733",
                "IGNORED_LINE",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("WORKER_PORT", raising=False)

    load_local_env(env_file)

    assert os.environ["DEEPSEEK_API_KEY"] == "test-key"
    assert os.environ["WORKER_PORT"] == "5733"


def test_load_local_env_does_not_override_existing_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "shell-key")

    load_local_env(env_file)

    assert os.environ["DEEPSEEK_API_KEY"] == "shell-key"
