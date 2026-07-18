"""Public API for pkg_billing.

The router lives here; configuration, HMAC signing, and the store are split
into sibling modules (``config``, ``signing``, ``store``). This module
re-exports the public surface so callers keep importing from
``pkg_billing.api``.
"""

from __future__ import annotations

import json
import logging
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pkg_auth.api import User, get_current_user
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from pkg_billing.config import (
    BillingConfig,
    BillingSettings,
    get_config,
    load_settings,
    reset_settings_cache,
)
from pkg_billing.signing import sign_ref, valid_stripe_signature, verify_ref
from pkg_billing.store import (
    BillingStore,
    LedgerCursor,
    UserId,
    get_billing_store,
    set_billing_store,
)

__all__ = [
    "BillingConfig",
    "BillingSettings",
    "BillingStore",
    "LedgerCursor",
    "UserId",
    "create_checkout_session",
    "get_billing_store",
    "get_config",
    "load_settings",
    "reset_settings_cache",
    "router",
    "set_billing_store",
]

logger = logging.getLogger(__name__)

SUPPORTED_EVENT_TYPES = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "refund.created",
    "charge.dispute.created",
    "charge.dispute.funds_reinstated",
}

PACK_MINUTES: dict[str, int] = {"small": 100, "large": 1000}


class CheckoutRequest(BaseModel):
    pack: Literal["small", "large"] = "small"


BillingCategory = Literal["all", "purchases", "usage", "adjustments"]

CATEGORY_ENTRY_TYPES: dict[BillingCategory, frozenset[str] | None] = {
    "all": None,
    "purchases": frozenset({"purchase"}),
    "usage": frozenset({"job_debit"}),
    "adjustments": frozenset({"refund", "dispute", "dispute_reinstated"}),
}


async def create_checkout_session(
    user: User,
    pack: Literal["small", "large"] | BillingConfig = "small",
    config: BillingConfig | None = None,
) -> str:
    """Create a Stripe Checkout Session and return its hosted checkout URL."""
    if isinstance(pack, BillingConfig):
        config = pack
        pack = "small"
    resolved_config = config or get_config()
    if resolved_config.stripe_secret is None or resolved_config.app_base_url is None:
        raise RuntimeError(
            "Checkout Sessions require STRIPE_SECRET, a pack price ID, and APP_BASE_URL"
        )
    price_id = (
        resolved_config.stripe_small_price_id
        if pack == "small"
        else resolved_config.stripe_large_price_id
    )
    if price_id is None:
        raise RuntimeError(f"Stripe price for {pack} pack is not configured")

    ref = sign_ref(str(user.id), resolved_config.ref_secret)
    app_base_url = resolved_config.app_base_url.rstrip("/")
    try:
        return await run_in_threadpool(
            _create_checkout_session_sync,
            api_key=resolved_config.stripe_secret,
            price_id=price_id,
            pack=pack,
            minutes=PACK_MINUTES[pack],
            client_reference_id=ref,
            customer_email=user.email,
            success_url=(f"{app_base_url}/?checkout=success&session_id={{CHECKOUT_SESSION_ID}}"),
            cancel_url=f"{app_base_url}/?checkout=cancel",
        )
    except Exception as exc:
        if _is_stripe_error(exc):
            raise RuntimeError("Stripe checkout is temporarily unavailable") from exc
        raise


router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/balance")
async def get_balance(
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[BillingStore, Depends(get_billing_store)],
) -> dict[str, int]:
    return await store.balance(user.id, load_settings().free_tier_monthly_limit)


@router.get("/history")
async def get_history(
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[BillingStore, Depends(get_billing_store)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: str | None = None,
    category: BillingCategory = "all",
) -> dict[str, object]:
    cursor = _decode_cursor(before) if before is not None else None
    rows = await store.list_ledger(
        user.id,
        limit,
        cursor=cursor,
        entry_types=CATEGORY_ENTRY_TYPES[category],
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1].created_at, page[-1].id) if has_more else None
    return {
        "entries": [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "entry_type": row.entry_type,
                "minutes_delta": row.minutes_delta,
                "usage_minutes": row.usage_minutes,
                "balance_after": row.balance_after,
                "pack": row.pack,
                "amount_cents": row.amount_cents,
                "currency": row.currency,
                "reason": row.reason,
                "receipt_url": row.receipt_url,
            }
            for row in page
        ],
        "has_more": has_more,
        "next_cursor": next_cursor,
    }


@router.get("/confirm")
async def confirm_purchase(
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[BillingStore, Depends(get_billing_store)],
    session_id: str,
) -> dict[str, bool]:
    return {"applied": await store.has_purchase(user.id, session_id)}


@router.post("/checkout")
async def checkout(
    user: Annotated[User, Depends(get_current_user)],
    store: Annotated[BillingStore, Depends(get_billing_store)],
    body: CheckoutRequest | None = None,
) -> dict[str, str]:
    pack = body.pack if body is not None else "small"
    try:
        config = get_config()
        if config.stripe_secret is None or config.stripe_small_price_id is None:
            raise RuntimeError(
                "Credit-pack checkout requires STRIPE_SECRET, STRIPE_SMALL_PRICE_ID, "
                "STRIPE_LARGE_PRICE_ID, and APP_BASE_URL"
            )
        url = await create_checkout_session(user, pack, config)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    await store.record_checkout_started(user.id, pack)
    return {"url": url}


@router.post("/webhook")
async def webhook(
    request: Request,
    store: Annotated[BillingStore, Depends(get_billing_store)],
) -> dict[str, bool]:
    config = get_config()
    if config.webhook_secret is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="STRIPE_WEBHOOK_SECRET is not configured",
        )
    body = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature or not valid_stripe_signature(body, signature, config.webhook_secret):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON") from exc

    await _handle_event(event, store, config)
    return {"ok": True}


def _create_checkout_session_sync(
    *,
    api_key: str,
    price_id: str,
    pack: str,
    minutes: int,
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
            metadata={"pack": pack, "minutes": str(minutes), "price_id": price_id},
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


async def _handle_event(event: dict[str, Any], store: BillingStore, config: BillingConfig) -> None:
    event_id = event.get("id")
    event_type = event.get("type")
    if not isinstance(event_id, str) or not isinstance(event_type, str):
        logger.warning("Ignoring Stripe event with missing id/type")
        return
    if event_type not in SUPPORTED_EVENT_TYPES:
        return

    data = event.get("data")
    session_object: object | None = None
    if isinstance(data, dict):
        typed_data = cast(dict[str, Any], data)
        session_object = typed_data.get("object")
    if not isinstance(session_object, dict):
        logger.warning("Ignoring Stripe event %s with malformed session", event_id)
        return
    stripe_object = cast(dict[str, Any], session_object)
    if event_type == "refund.created":
        refund_id = _string(stripe_object.get("id"))
        amount = _integer(stripe_object.get("amount"))
        if refund_id is None or amount is None:
            return
        await store.apply_refund_once(
            event_id=event_id,
            refund_id=refund_id,
            amount_cents=amount,
            payment_intent_id=_payment_intent_id(stripe_object),
            charge_id=_object_id(stripe_object.get("charge")),
            reason=_string(stripe_object.get("reason")),
            created_at=_paid_at(event),
        )
        return
    if event_type in {"charge.dispute.created", "charge.dispute.funds_reinstated"}:
        dispute_id = _string(stripe_object.get("id"))
        if dispute_id is None:
            return
        await store.apply_dispute_once(
            event_id=event_id,
            dispute_id=dispute_id,
            payment_intent_id=_payment_intent_id(stripe_object),
            charge_id=_object_id(stripe_object.get("charge")),
            reason=_string(stripe_object.get("reason")),
            reinstated=event_type == "charge.dispute.funds_reinstated",
            created_at=_paid_at(event),
        )
        return

    session = stripe_object
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

    pack_info = _pack_info(session, config)
    amount_cents = _integer(session.get("amount_total"))
    currency = _string(session.get("currency"))
    if pack_info is None or amount_cents is None or currency is None:
        logger.warning("Ignoring Stripe session %s without trusted pack metadata", session_id)
        return
    pack, minutes = pack_info
    applied = await store.apply_purchase_once(
        event_id=event_id,
        session_id=session_id,
        user_id=user.id,
        paid_at=_paid_at(event),
        pack=pack,
        minutes=minutes,
        amount_cents=amount_cents,
        currency=currency,
        payment_intent_id=_object_id(session.get("payment_intent")),
        charge_id=_object_id(session.get("charge")),
    )
    if not applied:
        logger.info("Ignoring already-processed Stripe event %s", event_id)
        return
    payment_intent_id = _object_id(session.get("payment_intent"))
    if payment_intent_id is None or config.stripe_secret is None:
        return
    try:
        receipt_url = await run_in_threadpool(
            _fetch_receipt_url_sync,
            payment_intent_id=payment_intent_id,
            api_key=config.stripe_secret,
        )
        if receipt_url is not None:
            await store.set_receipt_url(session_id, receipt_url)
    except Exception:
        logger.warning(
            "Could not enrich Stripe purchase receipt for session %s",
            session_id,
            exc_info=True,
        )


def _fetch_receipt_url_sync(*, payment_intent_id: str, api_key: str) -> str | None:
    import stripe

    payment_intent = stripe.PaymentIntent.retrieve(
        payment_intent_id,
        api_key=api_key,
        expand=["latest_charge"],
    )
    latest_charge = _object_field(payment_intent, "latest_charge")
    if isinstance(latest_charge, str):
        latest_charge = stripe.Charge.retrieve(latest_charge, api_key=api_key)
    return _string(_object_field(latest_charge, "receipt_url"))


def _object_field(value: object, key: str) -> object | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value).get(key)
    return getattr(value, key, None)


def _encode_cursor(created_at: datetime, entry_id: str) -> str:
    raw = f"{created_at.isoformat()}|{entry_id}".encode()
    return urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str) -> LedgerCursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = urlsafe_b64decode(padded.encode()).decode()
        created_at_raw, entry_id = decoded.rsplit("|", 1)
        if not entry_id:
            raise ValueError
        return LedgerCursor(datetime.fromisoformat(created_at_raw), entry_id)
    except (Base64Error, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid billing history cursor",
        ) from exc


def _pack_info(session: dict[str, Any], config: BillingConfig) -> tuple[str, int] | None:
    price: dict[str, Any] | None = None
    line_items = session.get("line_items")
    if isinstance(line_items, dict):
        data = cast(dict[str, object], line_items).get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            candidate = cast(dict[str, object], data[0]).get("price")
            if isinstance(candidate, dict):
                price = cast(dict[str, Any], candidate)
    metadata: dict[str, Any] | None = None
    price_id: str | None = None
    if price is not None:
        price_id = _string(price.get("id"))
        raw_metadata = price.get("metadata")
        if isinstance(raw_metadata, dict):
            metadata = cast(dict[str, Any], raw_metadata)
    if metadata is None:
        raw_metadata = session.get("metadata")
        if isinstance(raw_metadata, dict):
            metadata = cast(dict[str, Any], raw_metadata)
            price_id = _string(metadata.get("price_id"))
    if metadata is None:
        return None
    pack = _string(metadata.get("pack"))
    minutes_raw = metadata.get("minutes")
    if not isinstance(minutes_raw, str | int):
        return None
    try:
        minutes = int(minutes_raw)
    except (TypeError, ValueError):
        return None
    expected_price = {
        "small": config.stripe_small_price_id,
        "large": config.stripe_large_price_id,
    }.get(pack or "")
    if pack not in PACK_MINUTES or minutes != PACK_MINUTES[pack] or price_id != expected_price:
        return None
    return pack, minutes


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _object_id(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _string(cast(dict[str, object], value).get("id"))
    return None


def _payment_intent_id(value: dict[str, Any]) -> str | None:
    direct = _object_id(value.get("payment_intent"))
    if direct is not None:
        return direct
    charge = value.get("charge")
    if isinstance(charge, dict):
        return _object_id(cast(dict[str, object], charge).get("payment_intent"))
    return None


async def _resolve_user(
    session: dict[str, Any],
    store: BillingStore,
    ref_secret: str,
) -> User | None:
    user_id = verify_ref(session.get("client_reference_id"), ref_secret)
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
