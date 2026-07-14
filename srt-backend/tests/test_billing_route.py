"""Integration tests for pkg-billing mounted in the mono-app."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select


def test_billing_webhook_credits_shared_auth_store(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env

    _configure_billing_env(monkeypatch)

    from srt_backend.app import api

    with TestClient(api) as client:
        me = client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json() == {
            "email": "dev@example.test",
            "tier": "free",
            "is_admin": False,
        }

        event = _paid_event("evt_paid", "cs_paid", "")
        webhook = client.post(
            "/api/billing/webhook",
            content=_body(event),
            headers=_headers(event),
        )
        assert webhook.status_code == 200

        balance = client.get("/api/billing/balance")
        assert balance.status_code == 200
        assert balance.json() == {
            "free_limit": 2,
            "free_used": 0,
            "free_remaining": 2,
            "purchased_minutes": 100,
            "available_minutes": 102,
        }
        assert client.get("/api/auth/me").json()["tier"] == "free"


def test_purchased_balance_survives_restart(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env
    _configure_billing_env(monkeypatch)

    from srt_backend.app import api

    with TestClient(api) as client:
        event = _paid_event("evt_restart_paid", "cs_restart_paid", "")
        assert (
            client.post(
                "/api/billing/webhook",
                content=_body(event),
                headers=_headers(event),
            ).status_code
            == 200
        )

    with TestClient(api) as restarted:
        balance = restarted.get("/api/billing/balance")

    assert balance.status_code == 200
    assert balance.json()["purchased_minutes"] == 100


def test_duplicate_webhook_across_restart_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env
    _configure_billing_env(monkeypatch)

    from pkg_job_orch.api import CreditLedgerEntry, get_engine
    from srt_backend.app import api

    with TestClient(api) as client:
        event = _paid_event("evt_once_restart", "cs_once_restart", "")
        assert (
            client.post(
                "/api/billing/webhook",
                content=_body(event),
                headers=_headers(event),
            ).status_code
            == 200
        )

    with TestClient(api) as restarted:
        event = _paid_event("evt_second_delivery", "cs_once_restart", "")
        assert (
            restarted.post(
                "/api/billing/webhook",
                content=_body(event),
                headers=_headers(event),
            ).status_code
            == 200
        )
        assert restarted.get("/api/billing/balance").json()["purchased_minutes"] == 100
        with Session(get_engine()) as session:
            rows = session.exec(
                select(CreditLedgerEntry).where(CreditLedgerEntry.session_id == "cs_once_restart")
            ).all()

    assert len(rows) == 1


def test_processed_event_id_is_unique(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env
    _configure_billing_env(monkeypatch)

    from pkg_job_orch.api import ProcessedEvent, get_engine
    from srt_backend.app import api

    with TestClient(api):
        with Session(get_engine()) as session:
            first = ProcessedEvent(
                event_id="evt_unique",
                session_id="cs_1",
                user_id="dev-user",
                paid_at="2026-07-09T00:00:00+00:00",
            )
            duplicate = ProcessedEvent(
                event_id="evt_unique",
                session_id="cs_2",
                user_id="dev-user",
                paid_at="2026-07-09T00:00:00+00:00",
            )
            session.add(first)
            session.commit()
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                session.commit()


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
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
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
    assert calls[0]["price_id"] == "price_small"
    assert calls[0]["pack"] == "small"
    assert calls[0]["minutes"] == 100
    assert calls[0]["customer_email"] == "dev@example.test"
    assert calls[0]["success_url"] == "http://localhost:5730/?checkout=success"
    assert calls[0]["cancel_url"] == "http://localhost:5730/?checkout=cancel"


def test_apply_purchase_once_is_atomic_on_duplicate_session(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    """A duplicate Checkout Session credits exactly one pack."""
    del temp_env
    _configure_billing_env(monkeypatch)

    import asyncio

    from pkg_billing.api import get_billing_store
    from pkg_job_orch.api import CreditLedgerEntry, get_engine
    from pkg_job_orch.api import User as DbUser
    from sqlmodel import Session, select
    from srt_backend.app import api

    with TestClient(api):
        store = get_billing_store()
        paid_at = "2026-01-01T00:00:00+00:00"
        first = asyncio.run(
            store.apply_purchase_once(
                "evt_atomic",
                "cs_atomic",
                "dev-user",
                paid_at,
                pack="small",
                minutes=100,
                amount_cents=399,
                currency="usd",
                payment_intent_id="pi_atomic",
                charge_id="ch_atomic",
            )
        )
        second = asyncio.run(
            store.apply_purchase_once(
                "evt_atomic_redelivery",
                "cs_atomic",
                "dev-user",
                paid_at,
                pack="small",
                minutes=100,
                amount_cents=399,
                currency="usd",
                payment_intent_id="pi_atomic",
                charge_id="ch_atomic",
            )
        )

        assert first is True
        assert second is False
        with Session(get_engine()) as session:
            rows = session.exec(
                select(CreditLedgerEntry).where(CreditLedgerEntry.session_id == "cs_atomic")
            ).all()
            user = session.get(DbUser, "dev-user")

    assert len(rows) == 1
    assert user is not None
    assert user.tier == "free"
    assert user.purchased_minutes == 100


def _body(event: dict[str, Any]) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def _headers(event: dict[str, Any]) -> dict[str, str]:
    body = _body(event)
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode("ascii") + body
    signature = hmac.new(b"whsec_test", signed_payload, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={timestamp},v1={signature}"}


def _configure_billing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "dev@example.test")
    monkeypatch.setenv("DEV_USER_TIER", "free")
    monkeypatch.setenv("BILLING_PAYMENT_LINK", "https://buy.stripe.com/test_abc")
    monkeypatch.setenv("BILLING_REF_SECRET", "ref-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("FREE_TIER_MONTHLY_LIMIT", "2")
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")


def _paid_event(event_id: str, session_id: str, signed_ref: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "created": 1_700_000_000,
        "data": {
            "object": {
                "id": session_id,
                "payment_status": "paid",
                "client_reference_id": signed_ref,
                "customer_details": {"email": "dev@example.test"},
                "metadata": {
                    "pack": "small",
                    "minutes": "100",
                    "price_id": "price_small",
                },
                "amount_total": 399,
                "currency": "usd",
                "payment_intent": f"pi_{session_id}",
                "charge": f"ch_{session_id}",
            }
        },
    }
