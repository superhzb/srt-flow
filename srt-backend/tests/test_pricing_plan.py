from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pkg_job_orch.api import (
    CreditLedgerEntry,
    Job,
    User,
    balance_snapshot,
    debit_job_once,
    get_engine,
    reset_engine,
    run_migrations,
    session_scope,
    source_minutes,
)
from pkg_srt_services.api import Cue
from sqlmodel import Session, select
from srt_backend.app_store import AppStore


def test_source_minutes_uses_latest_cue_end_and_ceils() -> None:
    cues = [
        Cue(1, "00:00:00,000", "00:00:04,000", "first"),
        Cue(2, "00:00:05,000", "01:00:00,001", "last"),
    ]

    assert source_minutes(cues) == 61


async def test_purchase_refund_dispute_and_reinstatement_are_idempotent(
    temp_env: dict[str, str],
) -> None:
    database_url = temp_env["DATABASE_URL"]
    reset_engine()
    run_migrations(database_url)
    with Session(get_engine(database_url)) as session:
        session.add(User(id="buyer", email="buyer@example.test"))
        session.commit()

    store = AppStore(database_url)
    purchase_applied = await store.apply_purchase_once(
        event_id="evt_purchase",
        session_id="cs_pack",
        user_id="buyer",
        paid_at="2026-07-13T00:00:00+00:00",
        pack="small",
        minutes=100,
        amount_cents=399,
        currency="usd",
        payment_intent_id="pi_pack",
        charge_id="ch_pack",
    )
    duplicate_applied = await store.apply_purchase_once(
        event_id="evt_duplicate",
        session_id="cs_pack",
        user_id="buyer",
        paid_at="2026-07-13T00:00:00+00:00",
        pack="small",
        minutes=100,
        amount_cents=399,
        currency="usd",
        payment_intent_id="pi_pack",
        charge_id="ch_pack",
    )
    assert purchase_applied
    assert not duplicate_applied
    assert await store.apply_refund_once(
        event_id="evt_refund",
        refund_id="re_partial",
        amount_cents=200,
        payment_intent_id="pi_pack",
        charge_id="ch_pack",
        reason="requested_by_customer",
        created_at="2026-07-13T01:00:00+00:00",
    )
    assert not await store.apply_refund_once(
        event_id="evt_refund_duplicate",
        refund_id="re_partial",
        amount_cents=200,
        payment_intent_id="pi_pack",
        charge_id="ch_pack",
        reason="requested_by_customer",
        created_at="2026-07-13T01:00:00+00:00",
    )
    assert await store.apply_dispute_once(
        event_id="evt_dispute",
        dispute_id="dp_pack",
        payment_intent_id="pi_pack",
        charge_id="ch_pack",
        reason="fraudulent",
        reinstated=False,
        created_at="2026-07-13T02:00:00+00:00",
    )
    assert await store.apply_dispute_once(
        event_id="evt_reinstated",
        dispute_id="dp_pack",
        payment_intent_id="pi_pack",
        charge_id="ch_pack",
        reason=None,
        reinstated=True,
        created_at="2026-07-13T03:00:00+00:00",
    )

    with session_scope(database_url) as session:
        user = session.get(User, "buyer")
        assert user is not None
        assert user.purchased_minutes == 49
        entries = session.exec(
            select(CreditLedgerEntry).where(CreditLedgerEntry.user_id == "buyer")
        ).all()
        assert [entry.minutes_delta for entry in entries] == [100, -51, -49, 49]


def test_success_debit_consumes_free_minutes_before_purchased(
    temp_env: dict[str, str],
) -> None:
    database_url = temp_env["DATABASE_URL"]
    reset_engine()
    run_migrations(database_url)
    submitted_at = datetime(2026, 7, 13, tzinfo=UTC)
    with session_scope(database_url) as session:
        session.add(User(id="metered", email="metered@example.test", purchased_minutes=10))
        session.add(
            Job(
                id="job_metered",
                user_id="metered",
                status="done",
                worker="cloud",
                src_lang="en",
                source_minutes=25,
                created_at=submitted_at,
            )
        )

    with session_scope(database_url) as session:
        job = session.get(Job, "job_metered")
        assert job is not None
        assert debit_job_once(session, job, 20)
        assert not debit_job_once(session, job, 20)

    with session_scope(database_url) as session:
        user = session.get(User, "metered")
        assert user is not None
        assert user.purchased_minutes == 5
        july = balance_snapshot(session, "metered", 20, month="2026-07")
        august = balance_snapshot(session, "metered", 20, month="2026-08")
        assert july.free_remaining == 0
        assert july.available_minutes == 5
        assert august.free_remaining == 20
        assert august.available_minutes == 25


def test_paid_session_credits_pack_once_by_checkout_session(
    monkeypatch: pytest.MonkeyPatch,
    temp_env: dict[str, str],
) -> None:
    del temp_env
    reset_engine()
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("AUTH_MODE", "dev")
    monkeypatch.setenv("DEV_USER_EMAIL", "buyer@example.test")
    monkeypatch.setenv("BILLING_REF_SECRET", "ref-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
    monkeypatch.setenv("FREE_TIER_MONTHLY_LIMIT", "20")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")
    monkeypatch.delenv("BILLING_PAYMENT_LINK", raising=False)

    from pkg_billing.api import reset_settings_cache
    from srt_backend.app import api

    reset_settings_cache()
    session = {
        "id": "cs_small",
        "payment_status": "paid",
        "customer_details": {"email": "buyer@example.test"},
        "amount_total": 399,
        "currency": "usd",
        "payment_intent": "pi_small",
        "metadata": {"pack": "small", "minutes": "100", "price_id": "price_small"},
    }

    with TestClient(api) as client:
        for event_id in ("evt_complete", "evt_async_duplicate"):
            event = {
                "id": event_id,
                "type": "checkout.session.completed",
                "created": 1_700_000_000,
                "data": {"object": session},
            }
            body = json.dumps(event, separators=(",", ":")).encode()
            timestamp = int(time.time())
            digest = hmac.new(
                b"whsec_test",
                f"{timestamp}.".encode() + body,
                hashlib.sha256,
            ).hexdigest()
            response = client.post(
                "/api/billing/webhook",
                content=body,
                headers={"stripe-signature": f"t={timestamp},v1={digest}"},
            )
            assert response.status_code == 200

        assert client.get("/api/billing/balance").json() == {
            "free_limit": 20,
            "free_used": 0,
            "free_remaining": 20,
            "purchased_minutes": 100,
            "available_minutes": 120,
        }
