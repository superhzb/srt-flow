from __future__ import annotations

from typing import Any


def test_health_reports_running_commit(client: Any, monkeypatch: Any) -> None:
    monkeypatch.setenv("SRT_FLOW_COMMIT", "abc123")

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "commit": "abc123"}
