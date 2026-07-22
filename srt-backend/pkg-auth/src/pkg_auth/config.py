"""Runtime configuration for pkg-auth."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal, cast

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from pkg_auth.models import Tier

AuthMode = Literal["google", "dev"]
Environment = Literal["dev", "staging", "prod"]

_DEV_ADMIN_SESSION_SECRET = "srt-flow-dev-admin-session-secret"


class AuthConfigError(RuntimeError):
    """Raised when auth configuration is unsafe or incomplete."""


class AuthSettings(BaseSettings):
    """Auth settings loaded at runtime from the process environment."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    env: Environment = Field(default="dev", alias="ENV")
    auth_mode: AuthMode = Field(default="google", alias="AUTH_MODE")
    dev_user_email: str = Field(default="dev@local", alias="DEV_USER_EMAIL")
    dev_user_tier: Tier = Field(default="paid", alias="DEV_USER_TIER")

    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: SecretStr | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    google_redirect_uri: str = Field(
        default="http://localhost:5730/api/auth/google/callback",
        alias="GOOGLE_REDIRECT_URI",
    )
    google_client_json: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CLIENT_JSON", "GOOGLE_OAUTH_CLIENT_JSON"),
    )

    jwt_secret: SecretStr | None = Field(default=None, alias="JWT_SECRET")
    jwt_ttl_hours: int = Field(default=168, alias="JWT_TTL_HOURS")

    admin_subs: Annotated[frozenset[str], NoDecode] = Field(
        default_factory=frozenset,
        alias="ADMIN_SUBS",
    )
    admin_emails: Annotated[frozenset[str], NoDecode] = Field(
        default_factory=frozenset,
        alias="ADMIN_EMAILS",
    )
    allowed_subs: Annotated[frozenset[str], NoDecode] = Field(
        default_factory=frozenset,
        alias="ALLOWED_SUBS",
    )
    allowed_emails: Annotated[frozenset[str], NoDecode] = Field(
        default_factory=frozenset,
        alias="ALLOWED_EMAILS",
    )
    admin_session_secret: SecretStr | None = Field(
        default=None,
        alias="ADMIN_SESSION_SECRET",
    )

    app_redirect_path: str = Field(default="/", alias="APP_REDIRECT_PATH")
    session_cookie_name: str = Field(default="srt_session", alias="SESSION_COOKIE_NAME")
    csrf_cookie_name: str = Field(default="srt_oauth_state", alias="CSRF_COOKIE_NAME")

    @field_validator("dev_user_tier")
    @classmethod
    def _validate_dev_user_tier(cls, value: str) -> str:
        if value not in {"free", "paid"}:
            msg = "DEV_USER_TIER must be 'free' or 'paid'"
            raise ValueError(msg)
        return value

    @field_validator("jwt_ttl_hours")
    @classmethod
    def _validate_jwt_ttl_hours(cls, value: int) -> int:
        if value <= 0:
            msg = "JWT_TTL_HOURS must be positive"
            raise ValueError(msg)
        return value

    @field_validator(
        "admin_subs", "admin_emails", "allowed_subs", "allowed_emails", mode="before"
    )
    @classmethod
    def _parse_admin_allowlist(cls, value: object) -> frozenset[str]:
        if value is None:
            return frozenset()
        if isinstance(value, str):
            return frozenset(item.strip().casefold() for item in value.split(",") if item.strip())
        if isinstance(value, (set, frozenset, list, tuple)):
            return frozenset(str(item).strip().casefold() for item in value if str(item).strip())
        msg = "Admin allowlists must be comma-separated strings"
        raise ValueError(msg)

    @model_validator(mode="after")
    def _set_dev_admin_session_secret(self) -> AuthSettings:
        if self.env == "dev" and self.admin_session_secret is None:
            self.admin_session_secret = SecretStr(_DEV_ADMIN_SESSION_SECRET)
        return self

    @model_validator(mode="after")
    def _load_google_json(self) -> AuthSettings:
        if not self.google_client_json:
            return self

        payload = _parse_google_client_json(self.google_client_json)
        self.google_client_id = self.google_client_id or payload.get("client_id")
        secret = payload.get("client_secret")
        if self.google_client_secret is None and secret is not None:
            self.google_client_secret = SecretStr(secret)

        redirect_uris = payload.get("redirect_uris")
        if (
            self.google_redirect_uri == "http://localhost:5730/api/auth/google/callback"
            and isinstance(redirect_uris, list)
            and redirect_uris
            and isinstance(redirect_uris[0], str)
        ):
            self.google_redirect_uri = redirect_uris[0]
        return self

    @property
    def cookie_secure(self) -> bool:
        return self.env != "dev"

    def validate_runtime(self) -> None:
        if self.env in {"staging", "prod"} and self.auth_mode != "google":
            msg = "AUTH_MODE must be 'google' when ENV is staging or prod"
            raise AuthConfigError(msg)
        if self.env != "dev" and self.auth_mode == "dev":
            msg = "AUTH_MODE=dev is only allowed when ENV=dev"
            raise AuthConfigError(msg)
        if self.env != "dev" and self.admin_session_secret is None:
            msg = "Missing required auth config: ADMIN_SESSION_SECRET"
            raise AuthConfigError(msg)
        if self.env in {"staging", "prod"} and not self.admin_subs and not self.admin_emails:
            msg = "Missing required auth config: ADMIN_SUBS or ADMIN_EMAILS"
            raise AuthConfigError(msg)
        if self.auth_mode == "google":
            missing = [
                name
                for name, value in (
                    ("GOOGLE_CLIENT_ID", self.google_client_id),
                    ("GOOGLE_CLIENT_SECRET", self.google_client_secret),
                    ("JWT_SECRET", self.jwt_secret),
                )
                if value is None or value == ""
            ]
            if missing:
                msg = f"Missing required auth config: {', '.join(missing)}"
                raise AuthConfigError(msg)


def _parse_google_client_json(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        msg = "GOOGLE_CLIENT_JSON must be a JSON object"
        raise ValueError(msg)

    parsed = cast(dict[str, Any], data)
    web = parsed.get("web")
    installed = parsed.get("installed")
    if isinstance(web, dict):
        parsed = cast(dict[str, Any], web)
    elif isinstance(installed, dict):
        parsed = cast(dict[str, Any], installed)

    return parsed


def load_settings() -> AuthSettings:
    settings = AuthSettings()
    settings.validate_runtime()
    return settings
