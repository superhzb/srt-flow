"""CI-covered retention test: purge_old_jobs against the booted app schema.

The pkg-job-orch suite has finer-grained unit tests, but the backend CI job
only collects ``srt-backend/tests`` — this drives the purge through the real
migrated schema + on-disk storage the app uses.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from pkg_file_upload.api import LocalStorage
from pkg_job_orch.api import DEV_USER_ID, Job, purge_old_jobs, session_scope


def test_purge_old_jobs_removes_row_and_files(client: Any) -> None:
    storage = LocalStorage(os.environ["STORAGE_ROOT"])
    now = datetime.now(UTC)
    with session_scope() as session:
        session.add(
            Job(
                id="stale",
                user_id=DEV_USER_ID,
                worker="mlx",
                src_lang="en",
                tgt_langs="fr",
                created_at=now - timedelta(days=60),
            )
        )
        session.add(
            Job(
                id="recent",
                user_id=DEV_USER_ID,
                worker="mlx",
                src_lang="en",
                tgt_langs="fr",
                created_at=now - timedelta(days=1),
            )
        )
    storage.save(DEV_USER_ID, "stale", "input.srt", b"stale")
    storage.save(DEV_USER_ID, "recent", "input.srt", b"recent")

    with session_scope() as session:
        purged = purge_old_jobs(session, storage, retention_days=30, now=now)

    assert purged == 1
    with session_scope() as session:
        assert session.get(Job, "stale") is None
        assert session.get(Job, "recent") is not None
    assert not (storage.root / DEV_USER_ID / "stale").exists()
    assert (storage.root / DEV_USER_ID / "recent" / "input.srt").exists()
