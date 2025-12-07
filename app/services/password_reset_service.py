"""Password reset helpers coordinating auth links + Calibre state."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from app.db.repositories import reset_passwords_repo
from app.services import calibre_users_service
from app.services.auth_link_service import (
    AuthLinkError,
    PayloadValidationError,
    TokenDecodeError,
    TokenExpiredError,
    decode_payload,
    encode_payload,
)
from app.utils.identity import normalize_email
from app.utils.logging import get_logger

LOG = get_logger("password_reset_service")
_INITIAL = "initial"
_RESET = "reset"


class PasswordResetError(RuntimeError):
    """Base error for password reset workflows."""


class PendingResetNotFoundError(PasswordResetError):
    """Raised when no reset/initial token exists for the email."""


@dataclass(frozen=True)
class PendingReset:
    email: str
    token_type: str
    book_ids: List[int]
    temp_password: Optional[str]
    issued_at: str


def _require_email(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized:
        raise PasswordResetError("email_required")
    return normalized


def _sanitize_book_ids(book_ids: Optional[Any]) -> List[int]:
    if book_ids is None:
        return []
    if not isinstance(book_ids, list):
        raise PasswordResetError("book_ids_invalid")
    try:
        return [int(value) for value in book_ids]
    except (TypeError, ValueError) as exc:
        raise PasswordResetError("book_ids_invalid") from exc


def _store_initial_password(email: str, plaintext_password: str) -> None:
    password_hash = generate_password_hash(plaintext_password)
    reset_passwords_repo.upsert_token(
        email=email,
        token_type=_INITIAL,
        password_hash=password_hash,
    )


def issue_initial_token(*, email: str, temp_password: str, book_ids: Optional[List[int]] = None) -> str:
    """Persist the generated password and return an auth link token."""

    normalized = _require_email(email)
    if not temp_password:
        raise PasswordResetError("temp_password_required")

    _store_initial_password(normalized, temp_password)

    document = {
        "email": normalized,
        "temp_password": temp_password,
        "book_ids": _sanitize_book_ids(book_ids),
    }
    try:
        token = encode_payload(document)
    except PayloadValidationError as exc:  # pragma: no cover - sanity guard
        raise PasswordResetError(str(exc)) from exc
    LOG.info("Issued initial auth token email=%s", normalized)
    return token


def issue_reset_token(*, email: str, book_ids: Optional[List[int]] = None) -> str:
    """Generate a reset-only token (expires after 24h)."""

    normalized = _require_email(email)
    user = calibre_users_service.lookup_user_by_email(normalized)
    if not user or not user.get("id"):
        raise PendingResetNotFoundError("user_not_found")

    reset_passwords_repo.upsert_token(email=normalized, token_type=_RESET, password_hash=None)

    document = {
        "email": normalized,
        "temp_password": None,
        "book_ids": _sanitize_book_ids(book_ids),
    }
    try:
        token = encode_payload(document)
    except PayloadValidationError as exc:  # pragma: no cover - sanity guard
        raise PasswordResetError(str(exc)) from exc
    LOG.info("Issued reset auth token email=%s", normalized)
    return token


def resolve_pending_reset(*, email: str, token: str) -> PendingReset:
    """Validate auth token + persistence to drive /login override flows."""

    normalized = _require_email(email)
    if not token:
        raise PasswordResetError("token_required")

    try:
        payload = decode_payload(token)
    except (TokenDecodeError, TokenExpiredError) as exc:
        raise PasswordResetError(str(exc)) from exc

    if payload["email"] != normalized:
        raise PasswordResetError("email_token_mismatch")

    token_type = _INITIAL if payload.get("temp_password") else _RESET
    record = reset_passwords_repo.get_token(email=normalized, token_type=token_type)
    if not record:
        raise PendingResetNotFoundError("pending_reset_missing")

    if token_type == _INITIAL:
        stored_hash = getattr(record, "password_hash", None)
        if not stored_hash:
            raise PendingResetNotFoundError("initial_token_missing_password")
        if not payload.get("temp_password"):
            raise PendingResetNotFoundError("payload_missing_temp_password")
        if not check_password_hash(stored_hash, payload["temp_password"]):
            raise PasswordResetError("temp_password_mismatch")

    return PendingReset(
        email=normalized,
        token_type=token_type,
        book_ids=list(payload.get("book_ids", [])),
        temp_password=payload.get("temp_password"),
        issued_at=payload.get("issued_at"),
    )


def _delete_token(email: str, token_type: str) -> None:
    try:
        removed = reset_passwords_repo.delete_token(email=email, token_type=token_type)
        if removed:
            LOG.info("Cleared %s token email=%s", token_type, email)
    except Exception:  # pragma: no cover - defensive logging
        LOG.warning("Failed clearing %s token email=%s", token_type, email, exc_info=True)


def complete_password_change(*, email: str, new_password: str) -> Dict[str, Optional[str]]:
    """Update Calibre password then clear stored tokens."""

    normalized = _require_email(email)
    user = calibre_users_service.lookup_user_by_email(normalized)
    if not user or not user.get("id"):
        raise PendingResetNotFoundError("user_not_found")

    updated = calibre_users_service.update_user_password(int(user["id"]), new_password)
    _delete_token(normalized, _INITIAL)
    _delete_token(normalized, _RESET)
    return updated


def purge_expired_records(*, older_than_days: int = 30) -> int:
    """Expose manual pruning for admin flows/tests."""

    return reset_passwords_repo.purge_expired_tokens(older_than_days=older_than_days)


def has_pending_token(*, email: str, initial: bool) -> bool:
    normalized = _require_email(email)
    token_type = _INITIAL if initial else _RESET
    record = reset_passwords_repo.get_token(email=normalized, token_type=token_type)
    return record is not None


__all__ = [
    "issue_initial_token",
    "issue_reset_token",
    "resolve_pending_reset",
    "complete_password_change",
    "purge_expired_records",
    "has_pending_token",
    "PendingReset",
    "PasswordResetError",
    "PendingResetNotFoundError",
]
