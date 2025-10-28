"""Calibre user helpers for Mozello order workflows."""
from __future__ import annotations

import secrets
from typing import Dict, Iterable, Optional, Tuple

from sqlalchemy import func
from werkzeug.security import generate_password_hash

from app.utils.identity import normalize_email
from app.utils.logging import get_logger

LOG = get_logger("calibre_users_service")

try:  # runtime dependency on embedded Calibre-Web modules
    from cps import ub, helper, config as cw_config  # type: ignore
except Exception:  # pragma: no cover - running outside Calibre-Web runtime
    ub = None  # type: ignore
    helper = None  # type: ignore
    cw_config = None  # type: ignore


class CalibreUnavailableError(RuntimeError):
    """Raised when Calibre-Web runtime resources are not available."""


class UserAlreadyExistsError(RuntimeError):
    """Raised when attempting to create a user for an email that already exists."""


class UserCreationError(RuntimeError):
    """Raised when user creation fails unexpectedly."""


class MailConfigMissingError(RuntimeError):
    """Raised when SMTP settings are missing for password reset emails."""


class PasswordResetError(RuntimeError):
    """Raised when password reset workflow fails unexpectedly."""


def _ensure_runtime() -> None:
    if ub is None or getattr(ub, "session", None) is None:
        raise CalibreUnavailableError("Calibre-Web session not available")


def _session():
    return getattr(ub, "session", None)


def lookup_users_by_emails(emails: Iterable[str]) -> Dict[str, Dict[str, Optional[str]]]:
    """Return mapping of normalized email -> user info for provided addresses."""
    sess = _session()
    if not sess:
        return {}
    normalized = {normalize_email(e) for e in emails if normalize_email(e)}
    if not normalized:
        return {}
    rows = (
        sess.query(ub.User)
        .filter(func.lower(ub.User.email).in_([e for e in normalized]))
        .all()
    )
    out: Dict[str, Dict[str, Optional[str]]] = {}
    for user in rows:
        mail = normalize_email(user.email)
        if not mail:
            continue
        out[mail] = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        }
    return out


def lookup_user_by_email(email: str) -> Optional[Dict[str, Optional[str]]]:
    normalized = normalize_email(email)
    if not normalized:
        return None
    return lookup_users_by_emails([normalized]).get(normalized)





def _generate_password() -> str:
    if helper and hasattr(helper, "generate_random_password"):
        return helper.generate_random_password(getattr(cw_config, "config_password_min_length", 12))  # type: ignore[arg-type]
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%&*?"
    return "".join(secrets.choice(alphabet) for _ in range(16))


def _apply_defaults(user) -> None:  # pragma: no cover - simple assignments
    if cw_config is None:
        return
    user.role = getattr(cw_config, "config_default_role", 0)
    user.sidebar_view = getattr(cw_config, "config_default_show", 0)
    user.locale = getattr(cw_config, "config_default_locale", "en")
    user.default_language = getattr(cw_config, "config_default_language", "all")
    user.allowed_tags = getattr(cw_config, "config_allowed_tags", "")
    user.denied_tags = getattr(cw_config, "config_denied_tags", "")
    user.allowed_column_value = getattr(cw_config, "config_allowed_column_value", "")
    user.denied_column_value = getattr(cw_config, "config_denied_column_value", "")


def create_user_for_email(email: str, preferred_username: Optional[str] = None) -> Tuple[Dict[str, Optional[str]], str]:
    """Create a Calibre user for the given email.

    Returns a tuple of (user_info_dict, plaintext_password).
    """
    _ensure_runtime()
    normalized = normalize_email(email)
    if not normalized:
        raise ValueError("email_required")
    if lookup_user_by_email(normalized):
        raise UserAlreadyExistsError("User already exists for provided email")

    password_plain = _generate_password()
    if helper and hasattr(helper, "valid_password"):
        helper.valid_password(password_plain)
    password_hash = generate_password_hash(password_plain)

    # Use the full normalized email as the Calibre user name to ensure
    # predictable mapping between Mozello order emails and Calibre accounts.
    # This avoids username collisions and simplifies lookups.
    username = normalized

    user = ub.User()
    user.email = normalized
    user.name = username
    user.password = password_hash
    _apply_defaults(user)

    sess = _session()
    if not sess:
        raise CalibreUnavailableError("Calibre session unavailable")
    sess.add(user)
    try:
        sess.commit()
    except Exception as exc:  # pragma: no cover - SQL error path
        sess.rollback()
        LOG.error("Failed creating Calibre user for email=%s: %s", normalized, exc)
        raise UserCreationError("Failed to create Calibre user") from exc

    info = {"id": user.id, "email": user.email, "name": user.name}
    return info, password_plain


def trigger_password_reset_email(user_id: int) -> str:
    """Trigger Calibre's password reset to email credentials to the user.

    Returns the Calibre user name when reset succeeds.
    """
    _ensure_runtime()
    if not helper or not hasattr(helper, "reset_password"):
        raise CalibreUnavailableError("password_reset_unavailable")

    reset_callable = getattr(helper, "reset_password", None)
    if not callable(reset_callable):  # pragma: no cover - defensive guard
        raise CalibreUnavailableError("password_reset_unavailable")

    result, user_name = reset_callable(user_id)
    if result == 1:
        LOG.info("Triggered Calibre password reset user_id=%s", user_id)
        return user_name or ""
    if result == 2:
        LOG.warning("Password reset skipped user_id=%s reason=mail_not_configured", user_id)
        raise MailConfigMissingError("mail_not_configured")

    LOG.error("Password reset failed user_id=%s status=%s", user_id, result)
    raise PasswordResetError("password_reset_failed")