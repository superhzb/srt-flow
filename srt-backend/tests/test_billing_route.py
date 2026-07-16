"""Integration tests for pkg-billing mounted in the mono-app."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
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
        assert me.json()["id"] == "dev-user"
        assert me.json()["email"] == "dev@example.test"
        assert me.json()["tier"] == "free"
        assert me.json()["is_admin"] is False
        assert isinstance(me.json()["created_at"], str)

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


def test_billing_checkout_uses_checkout_session_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env

    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "dev@example.test")
    monkeypatch.setenv("DEV_USER_TIER", "free")
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
    assert calls[0]["success_url"] == (
        "http://localhost:5730/?checkout=success&session_id={CHECKOUT_SESSION_ID}"
    )
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


def test_billing_history_uses_keyset_pagination_and_server_filters(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env
    _configure_billing_env(monkeypatch)

    from pkg_job_orch.api import CreditLedgerEntry, get_engine
    from srt_backend.app import api

    entries = [
        CreditLedgerEntry(
            id="purchase-c",
            user_id="dev-user",
            entry_type="purchase",
            minutes_delta=100,
            usage_minutes=0,
            balance_after=100,
            idempotency_key="history:purchase-c",
            pack="small",
            amount_cents=399,
            currency="usd",
            receipt_url="https://pay.example/receipt",
            created_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
        CreditLedgerEntry(
            id="free-usage",
            user_id="dev-user",
            entry_type="job_debit",
            minutes_delta=0,
            usage_minutes=7,
            balance_after=100,
            idempotency_key="history:free-usage",
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        CreditLedgerEntry(
            id="paid-usage",
            user_id="dev-user",
            entry_type="job_debit",
            minutes_delta=-3,
            usage_minutes=7,
            balance_after=97,
            idempotency_key="history:paid-usage",
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
        CreditLedgerEntry(
            id="purchase-b",
            user_id="dev-user",
            entry_type="purchase",
            minutes_delta=100,
            usage_minutes=0,
            balance_after=193,
            idempotency_key="history:purchase-b",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        CreditLedgerEntry(
            id="purchase-a",
            user_id="dev-user",
            entry_type="purchase",
            minutes_delta=100,
            usage_minutes=0,
            balance_after=293,
            idempotency_key="history:purchase-a",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        CreditLedgerEntry(
            id="adjustment-a",
            user_id="dev-user",
            entry_type="dispute_reinstated",
            minutes_delta=100,
            usage_minutes=0,
            balance_after=393,
            idempotency_key="history:adjustment-a",
            created_at=datetime(2025, 12, 31, tzinfo=UTC),
        ),
    ]

    with TestClient(api) as client:
        with Session(get_engine()) as session:
            session.add_all(entries)
            session.commit()

        first = client.get("/api/billing/history?limit=2")
        assert first.status_code == 200
        first_body = first.json()
        assert [row["id"] for row in first_body["entries"]] == [
            "purchase-c",
            "paid-usage",
        ]
        assert first_body["entries"][1]["usage_minutes"] == 7
        assert first_body["entries"][1]["minutes_delta"] == -3
        assert first_body["entries"][0]["receipt_url"] == "https://pay.example/receipt"
        assert first_body["has_more"] is True
        assert first_body["next_cursor"]

        with Session(get_engine()) as session:
            session.add(
                CreditLedgerEntry(
                    id="inserted-new",
                    user_id="dev-user",
                    entry_type="purchase",
                    minutes_delta=100,
                    idempotency_key="history:inserted-new",
                    created_at=datetime(2026, 1, 4, tzinfo=UTC),
                )
            )
            session.commit()

        second = client.get(
            "/api/billing/history",
            params={"limit": 2, "before": first_body["next_cursor"]},
        )
        assert second.status_code == 200
        assert [row["id"] for row in second.json()["entries"]] == [
            "purchase-b",
            "purchase-a",
        ]
        assert second.json()["has_more"] is True

        adjustments = client.get("/api/billing/history", params={"category": "adjustments"})
        assert [row["entry_type"] for row in adjustments.json()["entries"]] == [
            "dispute_reinstated"
        ]
        usage = client.get("/api/billing/history", params={"category": "usage"})
        assert [row["id"] for row in usage.json()["entries"]] == ["paid-usage"]
        assert client.get("/api/billing/history?limit=0").status_code == 422
        assert client.get("/api/billing/history?limit=101").status_code == 422


def test_billing_confirmation_is_session_and_user_scoped(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env
    _configure_billing_env(monkeypatch)

    import asyncio

    from pkg_auth.api import User, get_current_user
    from pkg_billing.api import get_billing_store
    from srt_backend.app import api

    with TestClient(api) as client:
        assert client.get("/api/billing/confirm?session_id=cs_confirm").json() == {"applied": False}
        store = get_billing_store()
        assert asyncio.run(
            store.apply_purchase_once(
                "evt_confirm",
                "cs_confirm",
                "dev-user",
                "2026-01-01T00:00:00+00:00",
                pack="small",
                minutes=100,
                amount_cents=399,
                currency="usd",
                payment_intent_id="pi_confirm",
                charge_id="ch_confirm",
            )
        )
        assert client.get("/api/billing/confirm?session_id=cs_confirm").json() == {"applied": True}

        async def other_user() -> User:
            return User(
                id="other-user",
                email="other@example.test",
                tier="free",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )

        api.dependency_overrides[get_current_user] = other_user
        try:
            assert client.get("/api/billing/confirm?session_id=cs_confirm").json() == {
                "applied": False
            }
        finally:
            api.dependency_overrides.pop(get_current_user, None)


def test_ledger_rows_keep_stripe_event_timestamps(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env
    _configure_billing_env(monkeypatch)

    import asyncio

    from pkg_billing.api import get_billing_store
    from srt_backend.app import api

    with TestClient(api):
        store = get_billing_store()
        assert asyncio.run(
            store.apply_purchase_once(
                "evt_timestamp_purchase",
                "cs_timestamp",
                "dev-user",
                "2026-01-03T00:00:00+00:00",
                pack="small",
                minutes=100,
                amount_cents=399,
                currency="usd",
                payment_intent_id="pi_timestamp",
                charge_id="ch_timestamp",
            )
        )
        assert asyncio.run(
            store.apply_refund_once(
                event_id="evt_timestamp_refund",
                refund_id="re_timestamp",
                amount_cents=100,
                payment_intent_id="pi_timestamp",
                charge_id="ch_timestamp",
                reason="partial refund",
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        assert asyncio.run(
            store.apply_dispute_once(
                event_id="evt_timestamp_dispute",
                dispute_id="dp_timestamp",
                payment_intent_id="pi_timestamp",
                charge_id="ch_timestamp",
                reason="dispute",
                reinstated=False,
                created_at="2026-01-02T00:00:00+00:00",
            )
        )

        rows = asyncio.run(store.list_ledger("dev-user", 10))

    assert [row.entry_type for row in rows] == [
        "purchase",
        "dispute",
        "refund",
    ]
    assert [row.created_at.date().isoformat() for row in rows] == [
        "2026-01-03",
        "2026-01-02",
        "2026-01-01",
    ]


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
