"""Integration test for DELETE /api/account (self-serve data erasure)."""

from __future__ import annotations

from typing import Any

from pkg_job_orch.api import DEV_USER_ID, Job, User, session_scope


def test_delete_account_204_and_removes_rows(client: Any) -> None:
    # The dev user is seeded by the lifespan. Give them a job first.
    with session_scope() as session:
        assert session.get(User, DEV_USER_ID) is not None
        session.add(
            Job(id="job-1", user_id=DEV_USER_ID, worker="mlx", src_lang="en", tgt_langs="fr")
        )

    resp = client.delete("/api/account")
    assert resp.status_code == 204
    # Session cookie is cleared on the response.
    assert "set-cookie" in {k.lower() for k in resp.headers}

    with session_scope() as session:
        assert session.get(User, DEV_USER_ID) is None
        assert session.get(Job, "job-1") is None
