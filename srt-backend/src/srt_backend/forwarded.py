"""Restore the public host/scheme when running behind the local router.

The brbot-router proxies with ``http-proxy``'s ``changeOrigin: true``, which
rewrites the upstream ``Host`` header to ``127.0.0.1:<port>``. uvicorn's
proxy-header handling restores the scheme from ``X-Forwarded-Proto`` but ignores
``X-Forwarded-Host``, so anything that builds *absolute* URLs from the live
request -- notably SQLAdmin's ``url_for`` -- points its CSS and nav links at
``127.0.0.1`` instead of the public domain, and the browser cannot load them.

This middleware rewrites the request host (and scheme) from the forwarded
headers, but only when the immediate peer is a trusted loopback proxy so it can
never be spoofed by a direct client.
"""

from __future__ import annotations

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["ForwardedHostMiddleware"]

_TRUSTED_CLIENTS = frozenset({"127.0.0.1", "::1"})


class ForwardedHostMiddleware:
    """Honor ``X-Forwarded-Host``/``X-Forwarded-Proto`` from a trusted proxy."""

    def __init__(self, app: ASGIApp, trusted_clients: frozenset[str] = _TRUSTED_CLIENTS) -> None:
        self.app = app
        self.trusted_clients = trusted_clients

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        if client is None or client[0] not in self.trusted_clients:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        forwarded_host = headers.get("x-forwarded-host")
        forwarded_proto = headers.get("x-forwarded-proto")

        if forwarded_host:
            # First hop wins for a comma-joined chain.
            MutableHeaders(scope=scope)["host"] = forwarded_host.split(",")[0].strip()
        if forwarded_proto:
            scope["scheme"] = forwarded_proto.split(",")[0].strip()

        await self.app(scope, receive, send)
