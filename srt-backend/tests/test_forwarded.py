"""ForwardedHostMiddleware restores the public host/scheme, but only for a
trusted loopback proxy -- a direct client cannot spoof the request host."""

from __future__ import annotations

import pytest
from srt_backend.forwarded import ForwardedHostMiddleware
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _app() -> Starlette:
    async def whoami(request: Request) -> JSONResponse:
        return JSONResponse({"url": str(request.url_for("whoami"))})

    app = Starlette(routes=[Route("/whoami", whoami, name="whoami")])
    app.add_middleware(ForwardedHostMiddleware)
    return app


@pytest.mark.parametrize(
    ("client", "expected"),
    [
        # Trusted loopback proxy: forwarded host/scheme win.
        ("127.0.0.1", "https://app.srt-flow.com/whoami"),
        # Untrusted peer: forwarded headers are ignored (no spoofing).
        ("203.0.113.7", "http://testserver/whoami"),
    ],
)
def test_forwarded_host_trust_boundary(client: str, expected: str) -> None:
    with TestClient(_app(), client=(client, 5000)) as c:
        resp = c.get(
            "/whoami",
            headers={
                "X-Forwarded-Host": "app.srt-flow.com",
                "X-Forwarded-Proto": "https",
            },
        )
    assert resp.json()["url"] == expected


def test_absent_headers_are_a_noop() -> None:
    with TestClient(_app(), client=("127.0.0.1", 5000)) as c:
        resp = c.get("/whoami")
    assert resp.json()["url"] == "http://testserver/whoami"


def test_first_host_in_chain_wins() -> None:
    with TestClient(_app(), client=("127.0.0.1", 5000)) as c:
        resp = c.get(
            "/whoami",
            headers={"X-Forwarded-Host": "app.srt-flow.com, internal:19205"},
        )
    assert resp.json()["url"] == "http://app.srt-flow.com/whoami"
