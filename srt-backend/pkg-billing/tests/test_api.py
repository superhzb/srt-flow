from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import time
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pkg_auth.api import User
from pkg_billing.api import (
    BillingConfig,
    check_quota,
    create_checkout_session,
    get_config,
    reset_settings_cache,
    router,
    set_billing_store,
)
from pkg_billing.api import (
    __all__ as public_names,
)

fetch_receipt_url_sync = cast(
    Callable[..., str | None],
    importlib.import_module("pkg_billing.api")._fetch_receipt_url_sync,
)


class _FakeBillingStore:
    """In-process BillingStore for unit tests (no DB)."""

    def __init__(
        self,
        users: list[User] | None = None,
        usage: dict[str | int, int] | None = None,
    ) -> None:
        self._users_by_id: dict[str, User] = {str(u.id): u for u in users or []}
        self._processed_events: set[str] = set()
        self._processed_sessions: set[str] = set()
        self._usage = dict(usage or {})
        self.purchase_records: list[dict[str, str | int | None]] = []
        self.checkout_records: list[dict[str, str | int]] = []
        self.receipt_records: dict[str, str] = {}

    async def get_by_id(self, user_id: str | int) -> User | None:
        return self._users_by_id.get(str(user_id))

    async def get_by_email(self, email: str) -> list[User]:
        return [user for user in self._users_by_id.values() if user.email == email]

    async def apply_purchase_once(
        self,
        event_id: str,
        session_id: str,
        user_id: str | int,
        paid_at: str,
        *,
        pack: str,
        minutes: int,
        amount_cents: int,
        currency: str,
        payment_intent_id: str | None,
        charge_id: str | None,
    ) -> bool:
        if session_id in self._processed_sessions:
            return False
        self._processed_events.add(event_id)
        self._processed_sessions.add(session_id)
        self.purchase_records.append(
            {
                "user_id": user_id,
                "event_id": event_id,
                "session_id": session_id,
                "paid_at": paid_at,
                "pack": pack,
                "minutes": minutes,
                "amount_cents": amount_cents,
                "currency": currency,
                "payment_intent_id": payment_intent_id,
                "charge_id": charge_id,
            }
        )
        return True

    async def apply_paid_webhook_once(
        self,
        event_id: str,
        session_id: str,
        user_id: str | int,
        paid_at: str,
    ) -> bool:
        del event_id, session_id, user_id, paid_at
        raise AssertionError("legacy paid-tier fulfillment must not be used")

    async def apply_refund_once(
        self,
        *,
        event_id: str,
        refund_id: str,
        amount_cents: int,
        payment_intent_id: str | None,
        charge_id: str | None,
        reason: str | None,
        created_at: str,
    ) -> bool:
        del (
            event_id,
            refund_id,
            amount_cents,
            payment_intent_id,
            charge_id,
            reason,
            created_at,
        )
        return False

    async def apply_dispute_once(
        self,
        *,
        event_id: str,
        dispute_id: str,
        payment_intent_id: str | None,
        charge_id: str | None,
        reason: str | None,
        reinstated: bool,
        created_at: str,
    ) -> bool:
        del (
            event_id,
            dispute_id,
            payment_intent_id,
            charge_id,
            reason,
            reinstated,
            created_at,
        )
        return False

    async def balance(self, user_id: str | int, free_limit: int) -> dict[str, int]:
        del user_id
        return {
            "free_limit": free_limit,
            "free_used": 0,
            "free_remaining": free_limit,
            "purchased_minutes": 0,
            "available_minutes": free_limit,
        }

    async def list_ledger(
        self,
        user_id: str | int,
        limit: int,
        cursor: object | None = None,
        entry_types: frozenset[str] | None = None,
    ) -> list[Any]:
        del user_id, limit, cursor, entry_types
        return []

    async def set_receipt_url(self, session_id: str, url: str) -> None:
        self.receipt_records[session_id] = url

    async def has_purchase(self, user_id: str | int, session_id: str) -> bool:
        return any(
            record["user_id"] == user_id and record["session_id"] == session_id
            for record in self.purchase_records
        )

    async def record_checkout_started(self, user_id: str | int, pack: str) -> None:
        self.checkout_records.append({"user_id": user_id, "pack": pack})

    async def has_processed_event(self, event_id: str) -> bool:
        return event_id in self._processed_events

    async def usage_count_this_period(self, user_id: str | int) -> int:
        return self._usage.get(user_id, self._usage.get(str(user_id), 0))


@pytest.fixture(autouse=True)
def billing_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("BILLING_REF_SECRET", "ref-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("FREE_TIER_MONTHLY_LIMIT", "2")
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")

    def no_receipt(**_kwargs: object) -> str | None:
        return None

    monkeypatch.setattr("pkg_billing.api._fetch_receipt_url_sync", no_receipt)
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_public_api_all_names_are_resolvable() -> None:
    mod = importlib.import_module("pkg_billing.api")
    for name in public_names:
        assert hasattr(mod, name), f"{name} in __all__ but not defined in api"


def test_checkout_session_config_loads_without_payment_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")

    config = get_config()

    assert config.stripe_secret == "sk_test_123"
    assert config.stripe_small_price_id == "price_small"
    assert config.stripe_large_price_id == "price_large"
    assert config.app_base_url == "http://localhost:5730"


def test_checkout_session_config_rejects_partial_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
    monkeypatch.delenv("APP_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="must be set together"):
        get_config()


def test_checkout_session_rejects_live_secret_outside_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("STRIPE_SECRET", "sk_live_123")
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")

    with pytest.raises(RuntimeError, match="Non-prod STRIPE_SECRET"):
        get_config()


def test_checkout_session_rejects_test_secret_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")

    with pytest.raises(RuntimeError, match="Prod STRIPE_SECRET"):
        get_config()


def test_checkout_session_accepts_live_secret_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("STRIPE_SECRET", "sk_live_123")
    monkeypatch.setenv("STRIPE_SMALL_PRICE_ID", "price_small")
    monkeypatch.setenv("STRIPE_LARGE_PRICE_ID", "price_large")
    monkeypatch.setenv("APP_BASE_URL", "https://example.com")

    config = get_config()

    assert config.stripe_secret == "sk_live_123"


def test_create_checkout_session_sends_signed_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    calls: list[dict[str, object]] = []

    def fake_create_checkout_session_sync(**kwargs: object) -> str:
        calls.append(kwargs)
        return "https://checkout.stripe.com/c/pay/cs_test_123"

    monkeypatch.setattr(
        "pkg_billing.api._create_checkout_session_sync",
        fake_create_checkout_session_sync,
    )
    user = User(id="42", google_sub="sub", email="user@example.com", tier="free")
    config = BillingConfig(
        env="dev",
        ref_secret="ref-secret",
        webhook_secret="whsec_test",
        free_tier_monthly_limit=2,
        stripe_secret="sk_test_123",
        stripe_small_price_id="price_small",
        stripe_large_price_id="price_large",
        app_base_url="http://localhost:5730/",
    )

    url = asyncio.run(create_checkout_session(user, config))

    assert url == "https://checkout.stripe.com/c/pay/cs_test_123"
    assert calls == [
        {
            "api_key": "sk_test_123",
            "price_id": "price_small",
            "pack": "small",
            "minutes": 100,
            "client_reference_id": _client_reference_id("42", "ref-secret"),
            "customer_email": "user@example.com",
            "success_url": (
                "http://localhost:5730/?checkout=success&session_id={CHECKOUT_SESSION_ID}"
            ),
            "cancel_url": "http://localhost:5730/?checkout=cancel",
        }
    ]


def test_check_quota_raises_402_when_free_limit_reached() -> None:
    import asyncio

    user = User(id="1", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user], usage={"1": 2})
    config = BillingConfig(
        env="dev",
        ref_secret="ref-secret",
        webhook_secret="whsec_test",
        free_tier_monthly_limit=2,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check_quota(user, store=store, config=config))

    assert exc_info.value.status_code == 402


def test_webhook_credits_signed_user_pack() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    ref = _client_reference_id(user.id, "ref-secret")
    event = _event(
        event_id="evt_1",
        session=_paid_session(
            "cs_1",
            client_reference_id=ref,
            customer_details={"email": "other@example.com"},
        ),
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert store.purchase_records == [
        {
            "user_id": "7",
            "event_id": "evt_1",
            "session_id": "cs_1",
            "paid_at": "2023-11-14T22:13:20+00:00",
            "pack": "small",
            "minutes": 100,
            "amount_cents": 399,
            "currency": "usd",
            "payment_intent_id": "pi_cs_1",
            "charge_id": "ch_cs_1",
        }
    ]


def test_webhook_rejects_bad_signature() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    event = _event(event_id="evt_bad", session={"id": "cs_bad", "payment_status": "paid"})

    post = getattr(client, "post")  # noqa: B009 - TestClient.post is untyped in pyright.
    response = post(
        "/api/billing/webhook",
        content=_body(event),
        headers={"stripe-signature": "t=1700000000,v1=bad"},
    )

    assert response.status_code == 400
    assert store.purchase_records == []


def test_webhook_does_not_trust_tampered_reference() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    other = User(id="8", google_sub="other", email="other@example.com", tier="free")
    store = _FakeBillingStore([user, other])
    client = _client(store)
    signed_for_7 = _client_reference_id("7", "ref-secret")
    tampered = f"OA.{signed_for_7.split('.', maxsplit=1)[1]}"
    event = _event(
        event_id="evt_tampered",
        session={
            "id": "cs_tampered",
            "payment_status": "paid",
            "client_reference_id": tampered,
            "customer_details": {"email": "ambiguous@example.com"},
        },
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert store.purchase_records == []


def test_webhook_uses_strict_email_fallback() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    event = _event(
        event_id="evt_email",
        session=_paid_session(
            "cs_email",
            customer_details={"email": "user@example.com"},
        ),
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert [record["user_id"] for record in store.purchase_records] == ["7"]


def test_webhook_marks_paid_on_async_payment_succeeded() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    ref = _client_reference_id(user.id, "ref-secret")
    event = _event(
        event_id="evt_async",
        session=_paid_session("cs_async", client_reference_id=ref),
        event_type="checkout.session.async_payment_succeeded",
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert [record["event_id"] for record in store.purchase_records] == ["evt_async"]


def test_webhook_ignores_unknown_event_types() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    event = _event(
        event_id="evt_unknown",
        session={"id": "pi_1", "payment_status": "paid"},
        event_type="payment_intent.created",
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert store.purchase_records == []


def test_webhook_skips_ambiguous_email_fallback() -> None:
    first = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    second = User(id="8", google_sub="other", email="user@example.com", tier="free")
    store = _FakeBillingStore([first, second])
    client = _client(store)
    event = _event(
        event_id="evt_ambiguous",
        session={
            "id": "cs_ambiguous",
            "payment_status": "paid",
            "customer_details": {"email": "user@example.com"},
        },
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert store.purchase_records == []


def test_webhook_is_idempotent_by_session_id() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    ref = _client_reference_id(user.id, "ref-secret")
    event = _event(
        event_id="evt_once",
        session=_paid_session("cs_once", client_reference_id=ref),
    )

    first = _post_webhook(client, event)
    second = _post_webhook(client, event)

    assert first == 200
    assert second == 200
    assert [record["event_id"] for record in store.purchase_records] == ["evt_once"]


def test_receipt_enrichment_failure_does_not_undo_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_receipt(**_kwargs: object) -> str | None:
        raise RuntimeError("stripe unavailable")

    monkeypatch.setattr("pkg_billing.api._fetch_receipt_url_sync", fail_receipt)
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    event = _event(
        event_id="evt_receipt_failure",
        session=_paid_session(
            "cs_receipt_failure",
            client_reference_id=_client_reference_id(user.id, "ref-secret"),
        ),
    )

    assert _post_webhook(client, event) == 200
    assert [row["session_id"] for row in store.purchase_records] == ["cs_receipt_failure"]
    assert store.receipt_records == {}


def test_webhook_persists_receipt_by_checkout_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def receipt(**_kwargs: object) -> str | None:
        return "https://pay.example/receipt"

    monkeypatch.setattr("pkg_billing.api._fetch_receipt_url_sync", receipt)
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    event = _event(
        event_id="evt_receipt",
        session=_paid_session(
            "cs_receipt",
            client_reference_id=_client_reference_id(user.id, "ref-secret"),
        ),
    )

    assert _post_webhook(client, event) == 200
    assert store.receipt_records == {"cs_receipt": "https://pay.example/receipt"}


def test_receipt_lookup_uses_expanded_charge_and_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stripe

    payment_calls: list[tuple[str, dict[str, object]]] = []

    def retrieve_payment(payment_intent_id: str, **kwargs: object) -> dict[str, object]:
        payment_calls.append((payment_intent_id, kwargs))
        return {"latest_charge": {"receipt_url": "https://pay.example/expanded"}}

    def unexpected_charge(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("expanded charge must not be retrieved again")

    monkeypatch.setattr(stripe.PaymentIntent, "retrieve", retrieve_payment)
    monkeypatch.setattr(stripe.Charge, "retrieve", unexpected_charge)

    assert (
        fetch_receipt_url_sync(payment_intent_id="pi_1", api_key="sk_test_123")
        == "https://pay.example/expanded"
    )
    assert payment_calls == [("pi_1", {"api_key": "sk_test_123", "expand": ["latest_charge"]})]


def test_receipt_lookup_retrieves_bare_charge_id_with_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stripe

    charge_calls: list[tuple[str, dict[str, object]]] = []

    def retrieve_payment(_payment_intent_id: str, **_kwargs: object) -> dict[str, object]:
        return {"latest_charge": "ch_1"}

    def retrieve_charge(charge_id: str, **kwargs: object) -> dict[str, object]:
        charge_calls.append((charge_id, kwargs))
        return {"receipt_url": "https://pay.example/bare"}

    monkeypatch.setattr(stripe.PaymentIntent, "retrieve", retrieve_payment)
    monkeypatch.setattr(stripe.Charge, "retrieve", retrieve_charge)

    assert (
        fetch_receipt_url_sync(payment_intent_id="pi_1", api_key="sk_test_123")
        == "https://pay.example/bare"
    )
    assert charge_calls == [("ch_1", {"api_key": "sk_test_123"})]


def _client(store: _FakeBillingStore) -> TestClient:
    set_billing_store(store)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def _post_webhook(client: TestClient, event: dict[str, Any]) -> int:
    post = getattr(client, "post")  # noqa: B009 - TestClient.post is untyped in pyright.
    response = post("/api/billing/webhook", content=_body(event), headers=_headers(event))
    return int(response.status_code)


def _event(
    event_id: str,
    session: dict[str, Any],
    event_type: str = "checkout.session.completed",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "type": event_type,
        "created": 1_700_000_000,
        "data": {"object": session},
    }


def _paid_session(session_id: str, **overrides: Any) -> dict[str, Any]:
    session: dict[str, Any] = {
        "id": session_id,
        "payment_status": "paid",
        "line_items": {
            "data": [
                {
                    "price": {
                        "id": "price_small",
                        "metadata": {"pack": "small", "minutes": "100"},
                    }
                }
            ]
        },
        "amount_total": 399,
        "currency": "usd",
        "payment_intent": f"pi_{session_id}",
        "charge": f"ch_{session_id}",
    }
    session.update(overrides)
    return session


def _body(event: dict[str, Any]) -> bytes:
    return json.dumps(event, separators=(",", ":")).encode("utf-8")


def _headers(event: dict[str, Any]) -> dict[str, str]:
    body = _body(event)
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.".encode("ascii") + body
    signature = hmac.new(b"whsec_test", signed_payload, hashlib.sha256).hexdigest()
    return {"stripe-signature": f"t={timestamp},v1={signature}"}


def _client_reference_id(user_id: str, secret: str) -> str:
    raw_user_id = user_id.encode("ascii")
    encoded_user_id = _b64url(raw_user_id)
    signature = hmac.new(secret.encode("utf-8"), raw_user_id, hashlib.sha256).digest()
    return f"{encoded_user_id}.{_b64url(signature)}"


def _b64url(raw: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
