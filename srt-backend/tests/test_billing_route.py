"""Integration tests for pkg-billing mounted in the mono-app."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient


def test_billing_checkout_and_webhook_flip_shared_auth_store(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env

    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "dev@example.test")
    monkeypatch.setenv("DEV_USER_TIER", "free")
    monkeypatch.setenv("BILLING_PAYMENT_LINK", "https://buy.stripe.com/test_abc")
    monkeypatch.setenv("BILLING_REF_SECRET", "ref-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("FREE_TIER_MONTHLY_LIMIT", "2")
    monkeypatch.setenv("STRIPE_SECRET", "")
    monkeypatch.setenv("STRIPE_PRICE_ID", "")
    monkeypatch.setenv("APP_BASE_URL", "")

    from srt_backend.app import api

    with TestClient(api) as client:
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json() == {"email": "dev@example.test", "tier": "free"}

        checkout = client.post("/api/billing/checkout")
        assert checkout.status_code == 200
        checkout_body = cast(dict[str, str], checkout.json())
        url = checkout_body["url"]
        params = parse_qs(urlsplit(url).query)
        signed_ref = params["client_reference_id"][0]
        assert url.startswith("https://buy.stripe.com/test_abc?")
        assert params["prefilled_email"] == ["dev@example.test"]

        event: dict[str, Any] = {
            "id": "evt_paid",
            "type": "checkout.session.completed",
            "created": 1_700_000_000,
            "data": {
                "object": {
                    "id": "cs_paid",
                    "payment_status": "paid",
                    "client_reference_id": signed_ref,
                    "customer_details": {"email": "dev@example.test"},
                }
            },
        }
        webhook = client.post(
            "/api/billing/webhook",
            content=_body(event),
            headers=_headers(event),
        )
        assert webhook.status_code == 200

        paid_me = client.get("/api/auth/me")
        assert paid_me.status_code == 200
        assert paid_me.json() == {"email": "dev@example.test", "tier": "paid"}


def test_billing_checkout_reports_placeholder_payment_link(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env

    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "dev@example.test")
    monkeypatch.setenv("DEV_USER_TIER", "free")
    monkeypatch.setenv("BILLING_PAYMENT_LINK", "https://buy.stripe.com/test_replace_me")
    monkeypatch.setenv("BILLING_REF_SECRET", "ref-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_SECRET", "")
    monkeypatch.setenv("STRIPE_PRICE_ID", "")
    monkeypatch.setenv("APP_BASE_URL", "")

    from srt_backend.app import api

    with TestClient(api) as client:
        checkout = client.post("/api/billing/checkout")

    assert checkout.status_code == 503
    assert checkout.json() == {
        "detail": "BILLING_PAYMENT_LINK must be set to a real Stripe Payment Link"
    }


def test_billing_checkout_uses_checkout_session_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env

    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "dev@example.test")
    monkeypatch.setenv("DEV_USER_TIER", "free")
    monkeypatch.delenv("BILLING_PAYMENT_LINK", raising=False)
    monkeypatch.setenv("BILLING_REF_SECRET", "ref-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")

    calls: list[dict[str, object]] = []

    def fake_create_checkout_session_sync(**kwargs: object) -> str:
        calls.append(kwargs)
        return "https://checkout.stripe.com/c/pay/cs_test_123"

    monkeypatch.setattr(
        "pkg_billing.api._create_checkout_session_sync",
        fake_create_checkout_session_sync,
    )

    from srt_backend.app import api

    with TestClient(api) as client:
        checkout = client.post("/api/billing/checkout")

    assert checkout.status_code == 200
    assert checkout.json() == {"url": "https://checkout.stripe.com/c/pay/cs_test_123"}
    assert calls
    assert calls[0]["api_key"] == "sk_test_123"
    assert calls[0]["price_id"] == "price_123"
    assert calls[0]["customer_email"] == "dev@example.test"
    assert calls[0]["success_url"] == "http://localhost:5730/?checkout=success"
    assert calls[0]["cancel_url"] == "http://localhost:5730/?checkout=cancel"


def _body(event: dict[str, Any]) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def _headers(event: dict[str, Any]) -> dict[str, str]:
    body = _body(event)
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode("ascii") + body
    signature = hmac.new(b"whsec_test", signed_payload, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={timestamp},v1={signature}"}
