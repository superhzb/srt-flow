"""Tests for pkg_file_upload.api — import only from package.api."""

from __future__ import annotations

from pathlib import Path

import pytest
from pkg_file_upload.api import LocalStorage, Storage, StorageError


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path)


def test_local_storage_implements_protocol(storage: LocalStorage) -> None:
    # runtime_checkable Protocol — verifies method names exist.
    assert isinstance(storage, Storage)


def test_save_then_get_round_trip(storage: LocalStorage, tmp_path: Path) -> None:
    data = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n"
    saved = storage.save("u1", "j1", "input.srt", data)
    # Saved path matches the documented layout.
    assert saved == str(tmp_path / "u1" / "j1" / "input.srt")
    assert storage.get("u1", "j1", "input.srt") == data


def test_save_creates_nested_dirs(storage: LocalStorage, tmp_path: Path) -> None:
    # Parent dirs must not pre-exist; save creates them.
    storage.save("u1", "j1", "input.srt", b"x")
    assert (tmp_path / "u1" / "j1" / "input.srt").is_file()


def test_save_overwrites_existing_file(storage: LocalStorage) -> None:
    storage.save("u1", "j1", "input.srt", b"old")
    storage.save("u1", "j1", "input.srt", b"new")
    assert storage.get("u1", "j1", "input.srt") == b"new"


def test_get_missing_raises(storage: LocalStorage) -> None:
    with pytest.raises(StorageError, match="not found"):
        storage.get("u1", "j1", "missing.srt")


def test_delete_removes_file(storage: LocalStorage) -> None:
    storage.save("u1", "j1", "input.srt", b"x")
    storage.delete("u1", "j1", "input.srt")
    with pytest.raises(StorageError):
        storage.get("u1", "j1", "input.srt")


def test_delete_missing_is_noop(storage: LocalStorage) -> None:
    # Should not raise.
    storage.delete("u1", "j1", "never-existed.srt")


def test_url_for_canonical_relative_path(storage: LocalStorage) -> None:
    assert storage.url_for("u1", "j1", "output.fr.srt") == "u1/j1/output.fr.srt"


def test_output_lang_layout(storage: LocalStorage, tmp_path: Path) -> None:
    # The documented multi-target output layout: output.<lang>.srt.
    storage.save("u1", "j1", "output.fr.srt", b"fr")
    storage.save("u1", "j1", "output.de.srt", b"de")
    assert (tmp_path / "u1" / "j1" / "output.fr.srt").is_file()
    assert (tmp_path / "u1" / "j1" / "output.de.srt").is_file()


@pytest.mark.parametrize(
    ("user_id", "job_id", "filename"),
    [
        ("", "j1", "input.srt"),
        ("u1", "", "input.srt"),
        ("u1", "j1", ""),
        ("u/1", "j1", "input.srt"),
        ("u1", "j/1", "input.srt"),
        ("u1", "j1", "in/put.srt"),
        ("u1", "j1", ".."),
    ],
)
def test_invalid_components_rejected(
    storage: LocalStorage, user_id: str, job_id: str, filename: str
) -> None:
    with pytest.raises(StorageError):
        storage.save(user_id, job_id, filename, b"x")


def test_delete_job_removes_directory(storage: LocalStorage, tmp_path: Path) -> None:
    storage.save("u1", "j1", "input.srt", b"x")
    storage.save("u1", "j1", "output.fr.srt", b"fr")
    storage.delete_job("u1", "j1")
    assert not (tmp_path / "u1" / "j1").exists()


def test_delete_job_missing_is_noop(storage: LocalStorage) -> None:
    storage.delete_job("u1", "never-existed")  # must not raise


if __name__ == "__main__":
    import pytest as _pytest

    raise SystemExit(_pytest.main([__file__]))
