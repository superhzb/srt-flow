from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from srt_backend.app import SpaStaticFiles


@pytest.fixture
def static_client(tmp_path: Path) -> TestClient:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<script src="/assets/app-abc123.js"></script>')
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log('built')")
    app = FastAPI()
    app.mount("/", SpaStaticFiles(directory=tmp_path, html=True))
    return TestClient(app)


def test_serves_hashed_assets_with_immutable_cache(static_client: TestClient) -> None:
    response = static_client.get("/assets/app-abc123.js")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"


def test_revalidates_html_and_falls_back_for_spa_routes(
    static_client: TestClient,
) -> None:
    response = static_client.get("/jobs/123")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "/assets/app-abc123.js" in response.text


def test_missing_asset_does_not_return_the_html_shell(static_client: TestClient) -> None:
    response = static_client.get("/assets/missing.js")

    assert response.status_code == 404
