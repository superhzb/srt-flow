"""Billing configuration.

Two types with distinct roles:
- ``BillingSettings`` — env-loaded via pydantic-settings (one consistent
  loading mechanism, converged with pkg-auth per REFACTOR_PLAN.md Phase 3 #12).
  Loaded once and ``lru_cache``-d so requests don't re-parse env (#13);
  ``reset_settings_cache`` lets tests re-read after monkeypatching.
- ``BillingConfig`` — the validated, immutable value object the router uses.
  Cross-field validation raises ``RuntimeError`` (preserves the contract tests
  assert on). ``stripe_webhook_secret`` is optional: a checkout-only deploy no
  longer needs it (Phase 3 #13 over-coupling fix); the webhook route asserts it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "BillingConfig",
    "BillingSettings",
    "get_config",
    "load_settings",
    "reset_settings_cache",
]


@dataclass(frozen=True, slots=True)
class BillingConfig:
    env: str
    payment_link: str | None
    ref_secret: str
    webhook_secret: str | None
    free_tier_monthly_limit: int
    stripe_secret: str | None = None
    stripe_price_id: str | None = None
    app_base_url: str | None = None


class BillingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: str = "dev"
    billing_payment_link: str | None = None
    billing_ref_secret: str | None = None
    stripe_webhook_secret: str | None = None
    free_tier_monthly_limit: int = 10
    stripe_secret: str | None = None
    stripe_price_id: str | None = None
    app_base_url: str | None = None

    @field_validator(
        "billing_payment_link",
        "billing_ref_secret",
        "stripe_webhook_secret",
        "stripe_secret",
        "stripe_price_id",
        "app_base_url",
        mode="before",
    )
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        # Treat an empty env value as unset (matches the prior _optional_env
        # semantics so STRIPE_SECRET="" means "not configured").
        return None if value == "" else value

    @field_validator("free_tier_monthly_limit", mode="before")
    @classmethod
    def _empty_int_to_default(cls, value: object) -> object:
        return 10 if value in ("", None) else value


@lru_cache(maxsize=1)
def load_settings() -> BillingSettings:
    """Load billing env settings once per process (Phase 3 #13 cache)."""
    return BillingSettings()


def reset_settings_cache() -> None:
    """Test hook: clear the cached settings so a re-read picks up new env."""
    load_settings.cache_clear()


def get_config() -> BillingConfig:
    """Build the validated ``BillingConfig`` from cached env settings."""
    settings = load_settings()

    ref_secret = settings.billing_ref_secret
    if not ref_secret:
        raise RuntimeError("BILLING_REF_SECRET is required")

    if settings.free_tier_monthly_limit < 0:
        raise RuntimeError("FREE_TIER_MONTHLY_LIMIT must be non-negative")

    stripe_secret = settings.stripe_secret
    stripe_price_id = settings.stripe_price_id
    app_base_url = settings.app_base_url
    checkout_fields = {
        "STRIPE_SECRET": stripe_secret,
        "STRIPE_PRICE_ID": stripe_price_id,
        "APP_BASE_URL": app_base_url,
    }
    configured = [name for name, value in checkout_fields.items() if value is not None]
    if configured and len(configured) != len(checkout_fields):
        raise RuntimeError("STRIPE_SECRET, STRIPE_PRICE_ID, and APP_BASE_URL must be set together")

    has_checkout_trio = (
        stripe_secret is not None and stripe_price_id is not None and app_base_url is not None
    )
    if has_checkout_trio:
        assert stripe_secret is not None and app_base_url is not None
        _validate_stripe_secret(settings.env, stripe_secret)
        _validate_app_base_url(app_base_url)

    payment_link = settings.billing_payment_link
    if has_checkout_trio:
        # Payment Link is optional when Checkout Sessions are configured.
        if payment_link is not None:
            _validate_payment_link(settings.env, payment_link)
    else:
        if payment_link is None:
            raise RuntimeError("BILLING_PAYMENT_LINK is required")
        _validate_payment_link(settings.env, payment_link)

    return BillingConfig(
        env=settings.env,
        payment_link=payment_link,
        ref_secret=ref_secret,
        webhook_secret=settings.stripe_webhook_secret,
        free_tier_monthly_limit=settings.free_tier_monthly_limit,
        stripe_secret=stripe_secret,
        stripe_price_id=stripe_price_id,
        app_base_url=app_base_url,
    )


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
