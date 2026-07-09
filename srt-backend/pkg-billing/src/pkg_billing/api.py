"""Public API for pkg_billing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Protocol, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pkg_auth.api import User, get_current_user
from starlette.concurrency import run_in_threadpool

__all__ = [
    "BillingConfig",
    "BillingStore",
    "InMemoryBillingStore",
    "check_quota",
    "create_checkout_session",
    "checkout_url",
    "get_billing_store",
    "get_config",
    "router",
    "set_billing_store",
]

logger = logging.getLogger(__name__)

SUPPORTED_EVENT_TYPES = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
}
SIGNATURE_TOLERANCE_SECONDS = 300


class BillingStore(Protocol):
    async def get_by_id(self, user_id: int) -> User | None: ...

    async def get_by_email(self, email: str) -> list[User]: ...

    async def mark_paid(
        self,
        user_id: int,
        *,
        event_id: str,
        session_id: str,
        paid_at: str,
    ) -> None: ...

    async def has_processed_event(self, event_id: str) -> bool: ...

    async def record_event(self, event_id: str) -> None: ...

    async def usage_count_this_period(self, user_id: int) -> int: ...


@dataclass(frozen=True, slots=True)
class BillingConfig:
    env: str
    payment_link: str | None
    ref_secret: str
    webhook_secret: str
    free_tier_monthly_limit: int
    stripe_secret: str | None = None
    stripe_price_id: str | None = None
    app_base_url: str | None = None


class InMemoryBillingStore:
    """Test/demonstration store for billing without a database."""

    def __init__(
        self,
        users: list[User] | None = None,
        usage: dict[int, int] | None = None,
    ) -> None:
        self._users_by_id = {user.id: user for user in users or []}
        self._processed_events: set[str] = set()
        self._usage = dict(usage or {})
        self.paid_records: list[dict[str, str | int]] = []

    async def get_by_id(self, user_id: int) -> User | None:
        return self._users_by_id.get(user_id)

    async def get_by_email(self, email: str) -> list[User]:
        return [user for user in self._users_by_id.values() if user.email == email]

    async def mark_paid(
        self,
        user_id: int,
        *,
        event_id: str,
        session_id: str,
        paid_at: str,
    ) -> None:
        user = self._users_by_id[user_id]
        self._users_by_id[user_id] = User(
            id=user.id,
            google_sub=user.google_sub,
            email=user.email,
            tier="paid",
        )
        self.paid_records.append(
            {
                "user_id": user_id,
                "event_id": event_id,
                "session_id": session_id,
                "paid_at": paid_at,
            }
        )

    async def has_processed_event(self, event_id: str) -> bool:
        return event_id in self._processed_events

    async def record_event(self, event_id: str) -> None:
        self._processed_events.add(event_id)

    async def usage_count_this_period(self, user_id: int) -> int:
        return self._usage.get(user_id, 0)


_billing_store: BillingStore = InMemoryBillingStore()


def set_billing_store(store: BillingStore) -> None:
    """Set the process-wide billing store dependency."""
    global _billing_store
    _billing_store = store


def get_billing_store() -> BillingStore:
    return _billing_store


def get_config() -> BillingConfig:
    """Load billing config from the environment at a runtime boundary."""
    env = os.environ.get("ENV", "dev")
    payment_link = _optional_env("BILLING_PAYMENT_LINK")
    ref_secret = _required_env("BILLING_REF_SECRET")
    webhook_secret = _required_env("STRIPE_WEBHOOK_SECRET")
    free_tier_monthly_limit = _int_env("FREE_TIER_MONTHLY_LIMIT", default=10)
    stripe_secret = _optional_env("STRIPE_SECRET")
    stripe_price_id = _optional_env("STRIPE_PRICE_ID")
    app_base_url = _optional_env("APP_BASE_URL")

    checkout_session_fields = {
        "STRIPE_SECRET": stripe_secret,
        "STRIPE_PRICE_ID": stripe_price_id,
        "APP_BASE_URL": app_base_url,
    }
    configured_session_fields = [
        name for name, value in checkout_session_fields.items() if value is not None
    ]
    if configured_session_fields and len(configured_session_fields) != len(checkout_session_fields):
        raise RuntimeError("STRIPE_SECRET, STRIPE_PRICE_ID, and APP_BASE_URL must be set together")

    if stripe_secret is not None and stripe_price_id is not None and app_base_url is not None:
        _validate_stripe_secret(env, stripe_secret)
        _validate_app_base_url(app_base_url)
    else:
        payment_link = _required_env("BILLING_PAYMENT_LINK")

    if payment_link is not None:
        _validate_payment_link(env, payment_link)

    return BillingConfig(
        env=env,
        payment_link=payment_link,
        ref_secret=ref_secret,
        webhook_secret=webhook_secret,
        free_tier_monthly_limit=free_tier_monthly_limit,
        stripe_secret=stripe_secret,
        stripe_price_id=stripe_price_id,
        app_base_url=app_base_url,
    )


def checkout_url(user: User) -> str:
    """Return the configured Payment Link with a signed user reference."""
    config = get_config()
    if config.payment_link is None:
        raise RuntimeError("BILLING_PAYMENT_LINK is required for Payment Link checkout")
    ref = _sign_ref(user.id, config.ref_secret)
    return _append_query(
        config.payment_link,
        {
            "client_reference_id": ref,
            "prefilled_email": user.email,
        },
    )


async def create_checkout_session(user: User, config: BillingConfig | None = None) -> str:
    """Create a Stripe Checkout Session and return its hosted checkout URL."""
    resolved_config = config or get_config()
    if (
        resolved_config.stripe_secret is None
        or resolved_config.stripe_price_id is None
        or resolved_config.app_base_url is None
    ):
        raise RuntimeError(
            "Checkout Sessions require STRIPE_SECRET, STRIPE_PRICE_ID, and APP_BASE_URL"
        )

    ref = _sign_ref(user.id, resolved_config.ref_secret)
    app_base_url = resolved_config.app_base_url.rstrip("/")
    try:
        return await run_in_threadpool(
            _create_checkout_session_sync,
            api_key=resolved_config.stripe_secret,
            price_id=resolved_config.stripe_price_id,
            client_reference_id=ref,
            customer_email=user.email,
            success_url=f"{app_base_url}/?checkout=success",
            cancel_url=f"{app_base_url}/?checkout=cancel",
        )
    except Exception as exc:
        if _is_stripe_error(exc):
            raise RuntimeError("Stripe checkout is temporarily unavailable") from exc
        raise


async def check_quota(
    user: User,
    store: BillingStore | None = None,
    config: BillingConfig | None = None,
) -> None:
    if user.tier == "paid":
        return

    resolved_config = config or get_config()
    resolved_store = store or get_billing_store()
    usage = await resolved_store.usage_count_this_period(user.id)
    if usage >= resolved_config.free_tier_monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Free tier monthly limit reached",
        )


router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/checkout")
async def checkout(user: Annotated[User, Depends(get_current_user)]) -> dict[str, str]:
    try:
        config = get_config()
        if config.stripe_secret is not None and config.stripe_price_id is not None:
            url = await create_checkout_session(user, config)
        else:
            url = checkout_url(user)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return {"url": url}


@router.post("/webhook")
async def webhook(
    request: Request,
    store: Annotated[BillingStore, Depends(get_billing_store)],
) -> dict[str, bool]:
    config = get_config()
    body = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature or not _valid_stripe_signature(body, signature, config.webhook_secret):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc

    await _handle_event(event, store, config)
    return {"ok": True}


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or value == "":
        raise RuntimeError(f"{name} is required")
    return value


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    return value


def _int_env(name: str, *, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if parsed < 0:
        raise RuntimeError(f"{name} must be non-negative")
    return parsed


def _validate_payment_link(env: str, payment_link: str) -> None:
    if not payment_link.startswith("https://buy.stripe.com/"):
        raise RuntimeError("BILLING_PAYMENT_LINK must be a Stripe Payment Link")
    if "replace_me" in payment_link:
        raise RuntimeError("BILLING_PAYMENT_LINK must be set to a real Stripe Payment Link")
    if env != "prod" and not payment_link.startswith("https://buy.stripe.com/test_"):
        raise RuntimeError("Non-prod BILLING_PAYMENT_LINK must be a test-mode Stripe Payment Link")


def _validate_stripe_secret(env: str, stripe_secret: str) -> None:
    if env != "prod" and not stripe_secret.startswith("sk_test_"):
        raise RuntimeError("Non-prod STRIPE_SECRET must be a test-mode Stripe secret key")


def _validate_app_base_url(app_base_url: str) -> None:
    parts = urlsplit(app_base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise RuntimeError("APP_BASE_URL must be an absolute http(s) URL")


def _create_checkout_session_sync(
    *,
    api_key: str,
    price_id: str,
    client_reference_id: str,
    customer_email: str,
    success_url: str,
    cancel_url: str,
) -> str:
    import stripe

    session = cast(
        object,
        stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            client_reference_id=client_reference_id,
            customer_email=customer_email,
            success_url=success_url,
            cancel_url=cancel_url,
            api_key=api_key,
        ),
    )
    url = (
        cast(dict[str, object], session).get("url")
        if isinstance(session, dict)
        else cast(object, getattr(session, "url", None))
    )
    if not isinstance(url, str) or url == "":
        raise RuntimeError("Stripe Checkout Session did not include a URL")
    return url


def _is_stripe_error(exc: Exception) -> bool:
    try:
        import stripe
    except ImportError:
        return False
    return isinstance(exc, stripe.StripeError)


def _append_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign_ref(user_id: int, secret: str) -> str:
    user_id_bytes = str(user_id).encode("ascii")
    digest = hmac.new(secret.encode("utf-8"), user_id_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(user_id_bytes)}.{_b64url_encode(digest)}"


def _verify_ref(ref: object, secret: str) -> int | None:
    if not isinstance(ref, str):
        return None
    parts = ref.split(".")
    if len(parts) != 2:
        return None
    encoded_user_id, encoded_sig = parts
    try:
        user_id_bytes = _b64url_decode(encoded_user_id)
        supplied_sig = _b64url_decode(encoded_sig)
    except (ValueError, UnicodeDecodeError):
        return None

    expected_sig = hmac.new(secret.encode("utf-8"), user_id_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(supplied_sig, expected_sig):
        return None

    try:
        return int(user_id_bytes.decode("ascii"))
    except ValueError:
        return None


def _valid_stripe_signature(body: bytes, signature_header: str, secret: str) -> bool:
    values: dict[str, list[str]] = {}
    for part in signature_header.split(","):
        name, separator, value = part.partition("=")
        if separator:
            values.setdefault(name, []).append(value)

    timestamps = values.get("t", [])
    signatures = values.get("v1", [])
    if not timestamps or not signatures:
        return False

    try:
        timestamp = int(timestamps[0])
    except ValueError:
        return False

    if abs(time.time() - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
        return False

    signed_payload = f"{timestamp}.".encode("ascii") + body
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)


async def _handle_event(event: dict[str, Any], store: BillingStore, config: BillingConfig) -> None:
    event_id = event.get("id")
    event_type = event.get("type")
    if not isinstance(event_id, str) or not isinstance(event_type, str):
        logger.warning("Ignoring Stripe event with missing id/type")
        return
    if event_type not in SUPPORTED_EVENT_TYPES:
        return
    if await store.has_processed_event(event_id):
        return

    data = event.get("data")
    session_object: object | None = None
    if isinstance(data, dict):
        typed_data = cast(dict[str, Any], data)
        session_object = typed_data.get("object")
    if not isinstance(session_object, dict):
        logger.warning("Ignoring Stripe event %s with malformed session", event_id)
        return
    session = cast(dict[str, Any], session_object)
    if session.get("payment_status") != "paid":
        return

    user = await _resolve_user(session, store, config.ref_secret)
    if user is None:
        logger.warning(
            "Ignoring paid Stripe session %s without a unique user match",
            session.get("id"),
        )
        return

    session_id = session.get("id")
    if not isinstance(session_id, str):
        logger.warning("Ignoring Stripe event %s with missing session id", event_id)
        return

    await store.mark_paid(
        user.id,
        event_id=event_id,
        session_id=session_id,
        paid_at=_paid_at(event),
    )
    await store.record_event(event_id)


async def _resolve_user(
    session: dict[str, Any],
    store: BillingStore,
    ref_secret: str,
) -> User | None:
    user_id = _verify_ref(session.get("client_reference_id"), ref_secret)
    if user_id is not None:
        return await store.get_by_id(user_id)

    email = _session_email(session)
    if email is None:
        return None
    matches = await store.get_by_email(email)
    if len(matches) != 1:
        return None
    return matches[0]


def _session_email(session: dict[str, Any]) -> str | None:
    customer_details = session.get("customer_details")
    if isinstance(customer_details, dict):
        details = cast(dict[str, Any], customer_details)
        email = details.get("email")
        if isinstance(email, str) and email:
            return email
    customer_email = session.get("customer_email")
    if isinstance(customer_email, str) and customer_email:
        return customer_email
    return None


def _paid_at(event: dict[str, Any]) -> str:
    created = event.get("created")
    if isinstance(created, int | float):
        return datetime.fromtimestamp(created, UTC).isoformat()
    return datetime.now(UTC).isoformat()
