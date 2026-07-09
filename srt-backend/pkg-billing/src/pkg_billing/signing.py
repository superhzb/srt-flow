"""HMAC signing helpers: signed user refs and Stripe webhook verification."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SIGNATURE_TOLERANCE_SECONDS = 300

__all__ = [
    "append_query",
    "sign_ref",
    "valid_stripe_signature",
    "verify_ref",
]


def sign_ref(user_id: str, secret: str) -> str:
    user_id_bytes = str(user_id).encode("ascii")
    digest = hmac.new(secret.encode("utf-8"), user_id_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(user_id_bytes)}.{_b64url_encode(digest)}"


def verify_ref(ref: object, secret: str) -> str | None:
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
        user_id = user_id_bytes.decode("ascii")
    except UnicodeDecodeError:
        return None
    return user_id or None


def valid_stripe_signature(body: bytes, signature_header: str, secret: str) -> bool:
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


def append_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padded = value + ("=" * (-len(value) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))
