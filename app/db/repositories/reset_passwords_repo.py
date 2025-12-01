"""Repository helpers for temporary password tokens."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.db import plugin_session
from app.db.models import ResetPasswordToken
from app.utils.logging import get_logger

LOG = get_logger("reset_passwords_repo")
_VALID_TOKEN_TYPES = {"initial", "reset"}
_RETENTION_DAYS = 30


def _validate_token_type(token_type: str) -> None:
    if token_type not in _VALID_TOKEN_TYPES:
        raise ValueError("invalid_token_type")


def _best_effort_prune(session: Session, *, older_than_days: int = _RETENTION_DAYS) -> None:
    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    try:
        session.query(ResetPasswordToken).filter(ResetPasswordToken.created_at < cutoff).delete(
            synchronize_session=False
        )
    except Exception:  # pragma: no cover - defensive guard
        LOG.warning("Failed pruning reset tokens", exc_info=True)


def upsert_token(
    *,
    email: str,
    token_type: str,
    password_hash: Optional[str] = None,
    last_sent_at: Optional[datetime] = None,
) -> ResetPasswordToken:
    """Create or update the token row for the provided email/type pair."""
    _validate_token_type(token_type)
    now = datetime.utcnow()
    with plugin_session() as session:
        _best_effort_prune(session)
        record = (
            session.query(ResetPasswordToken)
            .filter(
                ResetPasswordToken.email == email,
                ResetPasswordToken.token_type == token_type,
            )
            .one_or_none()
        )
        if record:
            if password_hash is not None:
                record.password_hash = password_hash
            record.last_sent_at = last_sent_at or now
            return record
        record = ResetPasswordToken(
            email=email,
            token_type=token_type,
            password_hash=password_hash,
            last_sent_at=last_sent_at or now,
        )
        session.add(record)
        return record


def get_token(*, email: str, token_type: str) -> Optional[ResetPasswordToken]:
    """Fetch a token row by email/type, returning None when missing."""
    _validate_token_type(token_type)
    with plugin_session() as session:
        _best_effort_prune(session)
        return (
            session.query(ResetPasswordToken)
            .filter(
                ResetPasswordToken.email == email,
                ResetPasswordToken.token_type == token_type,
            )
            .one_or_none()
        )


def delete_token(*, email: str, token_type: str) -> bool:
    """Delete the stored token row if it exists."""
    _validate_token_type(token_type)
    with plugin_session() as session:
        _best_effort_prune(session)
        record = (
            session.query(ResetPasswordToken)
            .filter(
                ResetPasswordToken.email == email,
                ResetPasswordToken.token_type == token_type,
            )
            .one_or_none()
        )
        if not record:
            return False
        session.delete(record)
        return True


def purge_expired_tokens(*, older_than_days: int = _RETENTION_DAYS) -> int:
    """Force a pruning pass for tokens older than the provided retention window."""
    if older_than_days <= 0:
        raise ValueError("older_than_days_positive")
    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    with plugin_session() as session:
        deleted = (
            session.query(ResetPasswordToken)
            .filter(ResetPasswordToken.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        return int(deleted or 0)


__all__ = [
    "upsert_token",
    "get_token",
    "delete_token",
    "purge_expired_tokens",
]
