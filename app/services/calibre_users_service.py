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


class LanguageUpdateError(RuntimeError):
    """Raised when updating the user's language preference fails."""


class UserNotFoundError(RuntimeError):
    """Raised when Calibre cannot locate the requested user."""


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
            "locale": getattr(user, "locale", None),
            "default_language": getattr(user, "default_language", None),
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


_LANGUAGE_ALIAS = {
    "en": "en",
    "eng": "en",
    "english": "en",
    "lv": "lv",
    "lav": "lv",
    "lvs": "lv",
    "lv-lv": "lv",
    "ru": "ru",
    "rus": "ru",
    "ru-ru": "ru",
}

_LANGUAGE_PREFS = {
    "en": {"locale": "en", "default_language": "eng"},
    "lv": {"locale": "lv", "default_language": "lav"},
    "ru": {"locale": "ru", "default_language": "rus"},
}


def _normalize_language_preference(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    sanitized = cleaned.replace("_", "-")
    primary = sanitized.split("-")[0]
    return _LANGUAGE_ALIAS.get(primary)


def _apply_language_preference(user, preferred_language: Optional[str]) -> Optional[str]:
    normalized = _normalize_language_preference(preferred_language)
    if not normalized:
        return None
    prefs = _LANGUAGE_PREFS.get(normalized)
    if not prefs:
        return None
    user.locale = prefs["locale"]
    user.default_language = prefs["default_language"]
    return normalized


def create_user_for_email(
    email: str,
    preferred_username: Optional[str] = None,
    preferred_language: Optional[str] = None,
) -> Tuple[Dict[str, Optional[str]], str]:
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

    display_name = (preferred_username or "").strip()
    username = display_name or normalized

    user = ub.User()
    user.email = normalized
    user.name = username
    user.password = password_hash
    _apply_defaults(user)
    _apply_language_preference(user, preferred_language)

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

    info = {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "locale": getattr(user, "locale", None),
        "default_language": getattr(user, "default_language", None),
    }
    return info, password_plain


def update_language_preference(
    user_id: int,
    preferred_language: Optional[str],
) -> Dict[str, Optional[str]]:
    """Persist the requested language preference for an existing user."""
    _ensure_runtime()
    sess = _session()
    if not sess:
        raise CalibreUnavailableError("Calibre session unavailable")
    user = sess.query(ub.User).filter(ub.User.id == user_id).one_or_none()
    if not user:
        raise UserNotFoundError("user_not_found")
    normalized = _apply_language_preference(user, preferred_language)
    if not normalized:
        raise LanguageUpdateError("unsupported_language")
    try:
        sess.commit()
    except Exception as exc:  # pragma: no cover - SQL error path
        sess.rollback()
        LOG.error("Failed updating language preference user_id=%s: %s", user_id, exc)
        raise LanguageUpdateError("update_language_failed") from exc
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "locale": getattr(user, "locale", None),
        "default_language": getattr(user, "default_language", None),
        "preferred_language": normalized,
    }


def update_user_password(user_id: int, plaintext_password: str) -> Dict[str, Optional[str]]:
    """Hash and store a new password for an existing Calibre user."""
    _ensure_runtime()
    if not plaintext_password:
        raise ValueError("password_required")
    if helper and hasattr(helper, "valid_password"):
        helper.valid_password(plaintext_password)
    sess = _session()
    if not sess:
        raise CalibreUnavailableError("Calibre session unavailable")
    user = sess.query(ub.User).filter(ub.User.id == user_id).one_or_none()
    if not user:
        raise UserNotFoundError("user_not_found")
    user.password = generate_password_hash(plaintext_password)
    try:
        sess.commit()
    except Exception as exc:  # pragma: no cover - SQL error path
        sess.rollback()
        LOG.error("Failed updating Calibre password user_id=%s: %s", user_id, exc)
        raise PasswordResetError("update_password_failed") from exc
    return {"id": user.id, "email": user.email, "name": user.name}


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