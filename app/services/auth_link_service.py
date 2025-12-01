"""Encryption helpers for login/auth links shared across flows."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from app.utils.identity import normalize_email
from app.utils.logging import get_logger

LOG = get_logger("auth_link_service")
_RESET_TOKEN_TTL = timedelta(hours=24)


class AuthLinkError(RuntimeError):
    """Base error for auth link failures."""


class SecretKeyUnavailableError(AuthLinkError):
    """Raised when the Calibre/Flask SECRET_KEY is missing."""


class TokenDecodeError(AuthLinkError):
    """Raised when a provided auth token cannot be decoded."""


class TokenExpiredError(AuthLinkError):
    """Raised when a reset token exceeded its allowed lifetime."""


class PayloadValidationError(AuthLinkError):
    """Raised when callers attempt to encode malformed payloads."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_timestamp(raw: str) -> datetime:
    candidate = raw
    if raw.endswith("Z"):
        candidate = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise TokenDecodeError("invalid_timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _derive_fernet_key(secret_value: Any) -> bytes:
    if secret_value is None:
        raise SecretKeyUnavailableError("secret_key_missing")
    if isinstance(secret_value, bytes):
        secret_bytes = secret_value
    else:
        secret_bytes = str(secret_value).encode("utf-8")
    digest = hashlib.sha256(secret_bytes).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet() -> Fernet:
    secret = current_app.config.get("SECRET_KEY")  # type: ignore[union-attr]
    return Fernet(_derive_fernet_key(secret))


def _sanitize_book_ids(book_ids: Optional[Any]) -> List[int]:
    if book_ids is None:
        return []
    if not isinstance(book_ids, list):
        raise TokenDecodeError("book_ids_invalid")
    try:
        return [int(value) for value in book_ids]
    except (TypeError, ValueError) as exc:
        raise TokenDecodeError("book_ids_invalid") from exc


def encode_payload(payload: Dict[str, Any]) -> str:
    """Encrypt the payload dict into a Fernet token."""

    normalized_email = normalize_email(payload.get("email"))
    if not normalized_email:
        raise PayloadValidationError("email_required")

    temp_password = payload.get("temp_password")
    if temp_password is not None and not isinstance(temp_password, str):
        raise PayloadValidationError("temp_password_invalid")

    issued_at = payload.get("issued_at")
    if issued_at is not None and not isinstance(issued_at, str):
        raise PayloadValidationError("issued_at_invalid")

    if not issued_at:
        issued_at = _format_timestamp(_utcnow())
    else:
        _parse_timestamp(issued_at)  # validate format

    try:
        sanitized_books = _sanitize_book_ids(payload.get("book_ids"))
    except TokenDecodeError as exc:  # pragma: no cover - encode validation reroute
        raise PayloadValidationError("book_ids_invalid") from exc

    document = {
        "email": normalized_email,
        "temp_password": temp_password,
        "book_ids": sanitized_books,
        "issued_at": issued_at,
    }
    encoded = _fernet().encrypt(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return encoded.decode("utf-8")


def decode_payload(token: str) -> Dict[str, Any]:
    """Return decrypted payload dict enforcing reset token TTLs."""

    if not token or not isinstance(token, str):
        raise TokenDecodeError("token_required")

    try:
        decrypted = _fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        LOG.warning("Rejected invalid auth link token", exc_info=True)
        raise TokenDecodeError("invalid_token") from exc

    try:
        payload = json.loads(decrypted.decode("utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - input integrity guard
        raise TokenDecodeError("invalid_payload") from exc

    normalized_email = normalize_email(payload.get("email"))
    if not normalized_email:
        raise TokenDecodeError("email_missing")

    temp_password = payload.get("temp_password")
    if temp_password is not None and not isinstance(temp_password, str):
        raise TokenDecodeError("temp_password_invalid")

    issued_at_raw = payload.get("issued_at")
    if not isinstance(issued_at_raw, str):
        raise TokenDecodeError("issued_at_missing")
    issued_at_value = _parse_timestamp(issued_at_raw)

    sanitized_books = _sanitize_book_ids(payload.get("book_ids"))

    if not temp_password:
        age = _utcnow() - issued_at_value
        if age > _RESET_TOKEN_TTL:
            raise TokenExpiredError("reset_token_expired")

    return {
        "email": normalized_email,
        "temp_password": temp_password,
        "book_ids": sanitized_books,
        "issued_at": issued_at_raw,
    }


__all__ = [
    "encode_payload",
    "decode_payload",
    "AuthLinkError",
    "SecretKeyUnavailableError",
    "TokenDecodeError",
    "TokenExpiredError",
    "PayloadValidationError",
]
