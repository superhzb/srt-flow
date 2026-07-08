"""Public API for pkg_file_upload.

Owns on-disk storage of translation artifacts (input/output ``.srt``).
Layout::

    {STORAGE_ROOT}/{user_id}/{job_id}/
        input.srt
        output.<lang>.srt

Only ``LocalStorage`` is shipped today — the seam (the ``Storage``
``Protocol``) exists so R2/S3 can drop in later with no caller change.
``pkg-job-orch`` is the only consumer; it never touches disk directly.

Config is loaded at a runtime boundary (``LocalStorage(root=...)``),
never at import. No I/O at import.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["LocalStorage", "Storage", "StorageError"]


class StorageError(RuntimeError):
    """Raised on storage failures (write, read, missing)."""


@runtime_checkable
class Storage(Protocol):
    """Artifact storage contract.

    Paths are derived, not caller-chosen: every artifact lives under
    ``{root}/{user_id}/{job_id}/`` and is addressed by *filename* only
    (e.g. ``input.srt``, ``output.fr.srt``). Implementations enforce the
    layout; callers never build paths.

    Bytes are the unit — SRT text is encoded/decoded by the caller.
    """

    def save(self, user_id: str, job_id: str, filename: str, data: bytes) -> str:
        """Write ``data`` to ``{root}/{user_id}/{job_id}/{filename}``.

        Returns the absolute path saved. Parent dirs are created.
        Overwrites if the file already exists (idempotent re-save).
        """
        ...

    def get(self, user_id: str, job_id: str, filename: str) -> bytes:
        """Read previously-saved bytes.

        Raises:
            StorageError: If the file does not exist or cannot be read.
        """
        ...

    def delete(self, user_id: str, job_id: str, filename: str) -> None:
        """Delete one artifact. Missing file is a no-op."""
        ...

    def url_for(self, user_id: str, job_id: str, filename: str) -> str:
        """Relative path identifier for the artifact.

        Not a direct disk path (those are never exposed to the web layer
        — downloads flow through an auth-gated FastAPI route). For
        ``LocalStorage`` this is the canonical
        ``{user_id}/{job_id}/{filename}`` string the download route
        resolves.
        """
        ...


class LocalStorage:
    """``Storage`` backed by the local filesystem under ``root``.

    ``root`` is created lazily on first ``save``. All public methods
    normalise ``user_id``/``job_id``/``filename`` through ``_path`` so
    the layout is enforced in one place.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, user_id: str, job_id: str, filename: str) -> Path:
        if not user_id or not job_id or not filename:
            raise StorageError("user_id, job_id, and filename are all required")
        if "/" in user_id or "/" in job_id or "/" in filename:
            raise StorageError("path components may not contain '/'")
        # Guard against absolute or parent-traversing filenames.
        if filename in {".", ".."}:
            raise StorageError(f"invalid filename: {filename!r}")
        return self._root / user_id / job_id / filename

    def save(self, user_id: str, job_id: str, filename: str, data: bytes) -> str:
        path = self._path(user_id, job_id, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError(f"failed to write {path}: {exc}") from exc
        return str(path)

    def get(self, user_id: str, job_id: str, filename: str) -> bytes:
        path = self._path(user_id, job_id, filename)
        if not path.is_file():
            raise StorageError(f"not found: {path}")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError(f"failed to read {path}: {exc}") from exc

    def delete(self, user_id: str, job_id: str, filename: str) -> None:
        path = self._path(user_id, job_id, filename)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise StorageError(f"failed to delete {path}: {exc}") from exc

    def url_for(self, user_id: str, job_id: str, filename: str) -> str:
        # Validate via _path (raises on bad components) — keeps url_for
        # and the read/write paths consistent.
        self._path(user_id, job_id, filename)
        return f"{user_id}/{job_id}/{filename}"

    def delete_job(self, user_id: str, job_id: str) -> None:
        """Remove an entire job directory. Missing dir is a no-op."""
        if not user_id or not job_id or "/" in user_id or "/" in job_id:
            raise StorageError("user_id and job_id are required, no '/'")
        path = self._root / user_id / job_id
        shutil.rmtree(path, ignore_errors=True)
