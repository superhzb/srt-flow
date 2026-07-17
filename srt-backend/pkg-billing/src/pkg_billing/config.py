"""Billing configuration.

Two types with distinct roles:
- ``BillingSettings`` — env-loaded via pydantic-settings (one consistent
  loading mechanism, converged with pkg-auth).
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
    ref_secret: str
    webhook_secret: str | None
    free_tier_monthly_limit: int
    stripe_secret: str | None = None
    stripe_small_price_id: str | None = None
    stripe_large_price_id: str | None = None
    app_base_url: str | None = None


class BillingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: str = "dev"
    billing_ref_secret: str | None = None
    stripe_webhook_secret: str | None = None
    free_tier_monthly_limit: int = 30
    stripe_secret: str | None = None
    stripe_small_price_id: str | None = None
    stripe_large_price_id: str | None = None
    app_base_url: str | None = None

    @field_validator(
        "billing_ref_secret",
        "stripe_webhook_secret",
        "stripe_secret",
        "stripe_small_price_id",
        "stripe_large_price_id",
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
        return 30 if value in ("", None) else value


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
    stripe_small_price_id = settings.stripe_small_price_id
    stripe_large_price_id = settings.stripe_large_price_id
    app_base_url = settings.app_base_url
    checkout_fields = {
        "STRIPE_SECRET": stripe_secret,
        "STRIPE_SMALL_PRICE_ID": stripe_small_price_id,
        "STRIPE_LARGE_PRICE_ID": stripe_large_price_id,
        "APP_BASE_URL": app_base_url,
    }
    configured = [name for name, value in checkout_fields.items() if value is not None]
    if configured and len(configured) != len(checkout_fields):
        raise RuntimeError(
            "STRIPE_SECRET, STRIPE_SMALL_PRICE_ID, STRIPE_LARGE_PRICE_ID, "
            "and APP_BASE_URL must be set together"
        )

    if stripe_secret is not None:
        assert app_base_url is not None
        _validate_stripe_secret(settings.env, stripe_secret)
        _validate_app_base_url(app_base_url)

    return BillingConfig(
        env=settings.env,
        ref_secret=ref_secret,
        webhook_secret=settings.stripe_webhook_secret,
        free_tier_monthly_limit=settings.free_tier_monthly_limit,
        stripe_secret=stripe_secret,
        stripe_small_price_id=stripe_small_price_id,
        stripe_large_price_id=stripe_large_price_id,
        app_base_url=app_base_url,
    )


def _validate_stripe_secret(env: str, stripe_secret: str) -> None:
    is_test = stripe_secret.startswith("sk_test_")
    is_live = stripe_secret.startswith("sk_live_")
    if env != "prod" and not is_test:
        raise RuntimeError("Non-prod STRIPE_SECRET must be a test-mode Stripe secret key")
    if env == "prod" and not is_live:
        raise RuntimeError("Prod STRIPE_SECRET must be a live-mode Stripe secret key")


def _validate_app_base_url(app_base_url: str) -> None:
    parts = urlsplit(app_base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise RuntimeError("APP_BASE_URL must be an absolute http(s) URL")
