from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pkg_auth.api import User
from pkg_billing.api import (
    BillingConfig,
    check_quota,
    checkout_url,
    create_checkout_session,
    get_config,
    reset_settings_cache,
    router,
    set_billing_store,
)
from pkg_billing.api import (
    __all__ as public_names,
)


class _FakeBillingStore:
    """In-process BillingStore for unit tests (no DB). Mirrors the atomic
    apply_paid_webhook_once contract so webhook idempotency is exercised
    without a SQLite round-trip."""

    def __init__(
        self,
        users: list[User] | None = None,
        usage: dict[str | int, int] | None = None,
    ) -> None:
        self._users_by_id: dict[str, User] = {str(u.id): u for u in users or []}
        self._processed_events: set[str] = set()
        self._usage = dict(usage or {})
        self.paid_records: list[dict[str, str | int]] = []

    async def get_by_id(self, user_id: str | int) -> User | None:
        return self._users_by_id.get(str(user_id))

    async def get_by_email(self, email: str) -> list[User]:
        return [user for user in self._users_by_id.values() if user.email == email]

    async def apply_paid_webhook_once(
        self,
        event_id: str,
        session_id: str,
        user_id: str | int,
        paid_at: str,
    ) -> bool:
        if event_id in self._processed_events:
            return False
        self._processed_events.add(event_id)
        key = str(user_id)
        user = self._users_by_id.get(key)
        if user is not None:
            user.tier = "paid"
            self._users_by_id[key] = user
        self.paid_records.append(
            {
                "user_id": user_id,
                "event_id": event_id,
                "session_id": session_id,
                "paid_at": paid_at,
            }
        )
        return True

    async def has_processed_event(self, event_id: str) -> bool:
        return event_id in self._processed_events

    async def usage_count_this_period(self, user_id: str | int) -> int:
        return self._usage.get(user_id, self._usage.get(str(user_id), 0))


@pytest.fixture(autouse=True)
def billing_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("BILLING_PAYMENT_LINK", "https://buy.stripe.com/test_abc")
    monkeypatch.setenv("BILLING_REF_SECRET", "ref-secret")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("FREE_TIER_MONTHLY_LIMIT", "2")
    reset_settings_cache()
    yield
    reset_settings_cache()


def test_public_api_all_names_are_resolvable() -> None:
    mod = importlib.import_module("pkg_billing.api")
    for name in public_names:
        assert hasattr(mod, name), f"{name} in __all__ but not defined in api"


def test_checkout_url_adds_signed_reference_and_email() -> None:
    user = User(id="42", google_sub="sub", email="user@example.com", tier="free")

    url = checkout_url(user)

    assert url.startswith("https://buy.stripe.com/test_abc?")
    assert "prefilled_email=user%40example.com" in url
    assert "client_reference_id=NDI." in url


def test_checkout_rejects_live_link_outside_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILLING_PAYMENT_LINK", "https://buy.stripe.com/6oUeVebSc4cocsra6Y8IU00")

    with pytest.raises(RuntimeError, match="Non-prod"):
        checkout_url(User(id="1", google_sub="sub", email="user@example.com", tier="free"))


def test_checkout_rejects_placeholder_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILLING_PAYMENT_LINK", "https://buy.stripe.com/test_replace_me")

    with pytest.raises(RuntimeError, match="real Stripe Payment Link"):
        checkout_url(User(id="1", google_sub="sub", email="user@example.com", tier="free"))


def test_checkout_session_config_does_not_require_payment_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BILLING_PAYMENT_LINK", raising=False)
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")

    config = get_config()

    assert config.payment_link is None
    assert config.stripe_secret == "sk_test_123"
    assert config.stripe_price_id == "price_123"
    assert config.app_base_url == "http://localhost:5730"


def test_checkout_session_config_rejects_partial_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRIPE_SECRET", "sk_test_123")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.delenv("APP_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="must be set together"):
        get_config()


def test_checkout_session_rejects_live_secret_outside_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STRIPE_SECRET", "sk_live_123")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_123")
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5730")

    with pytest.raises(RuntimeError, match="Non-prod STRIPE_SECRET"):
        get_config()


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
        payment_link=None,
        ref_secret="ref-secret",
        webhook_secret="whsec_test",
        free_tier_monthly_limit=2,
        stripe_secret="sk_test_123",
        stripe_price_id="price_123",
        app_base_url="http://localhost:5730/",
    )

    url = asyncio.run(create_checkout_session(user, config))

    assert url == "https://checkout.stripe.com/c/pay/cs_test_123"
    assert calls == [
        {
            "api_key": "sk_test_123",
            "price_id": "price_123",
            "client_reference_id": _client_reference_id("42", "ref-secret"),
            "customer_email": "user@example.com",
            "success_url": "http://localhost:5730/?checkout=success",
            "cancel_url": "http://localhost:5730/?checkout=cancel",
        }
    ]


def test_check_quota_raises_402_when_free_limit_reached() -> None:
    import asyncio

    user = User(id="1", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user], usage={"1": 2})
    config = BillingConfig(
        env="dev",
        payment_link="https://buy.stripe.com/test_abc",
        ref_secret="ref-secret",
        webhook_secret="whsec_test",
        free_tier_monthly_limit=2,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(check_quota(user, store=store, config=config))

    assert exc_info.value.status_code == 402


def test_webhook_marks_signed_user_paid() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    ref = _client_reference_id(user.id, "ref-secret")
    event = _event(
        event_id="evt_1",
        session={
            "id": "cs_1",
            "payment_status": "paid",
            "client_reference_id": ref,
            "customer_details": {"email": "other@example.com"},
        },
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert store.paid_records == [
        {
            "user_id": "7",
            "event_id": "evt_1",
            "session_id": "cs_1",
            "paid_at": "2023-11-14T22:13:20+00:00",
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
    assert store.paid_records == []


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
    assert store.paid_records == []


def test_webhook_uses_strict_email_fallback() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    event = _event(
        event_id="evt_email",
        session={
            "id": "cs_email",
            "payment_status": "paid",
            "customer_details": {"email": "user@example.com"},
        },
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert [record["user_id"] for record in store.paid_records] == ["7"]


def test_webhook_marks_paid_on_async_payment_succeeded() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    ref = _client_reference_id(user.id, "ref-secret")
    event = _event(
        event_id="evt_async",
        session={"id": "cs_async", "payment_status": "paid", "client_reference_id": ref},
        event_type="checkout.session.async_payment_succeeded",
    )

    status_code = _post_webhook(client, event)

    assert status_code == 200
    assert [record["event_id"] for record in store.paid_records] == ["evt_async"]


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
    assert store.paid_records == []


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
    assert store.paid_records == []


def test_webhook_is_idempotent_by_event_id() -> None:
    user = User(id="7", google_sub="sub", email="user@example.com", tier="free")
    store = _FakeBillingStore([user])
    client = _client(store)
    ref = _client_reference_id(user.id, "ref-secret")
    event = _event(
        event_id="evt_once",
        session={"id": "cs_once", "payment_status": "paid", "client_reference_id": ref},
    )

    first = _post_webhook(client, event)
    second = _post_webhook(client, event)

    assert first == 200
    assert second == 200
    assert [record["event_id"] for record in store.paid_records] == ["evt_once"]


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
