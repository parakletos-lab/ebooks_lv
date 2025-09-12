"""
utils.py

Utility helpers for the users_books plugin.

Responsibilities:
  - Session/user identity access (user_id, admin flag, email).
  - Email normalization.
  - Dynamic resolution of Calibre-Web's user model and lookups by email.
  - Lightweight permission helper (ensure_admin).
  - Safe fallbacks if upstream structures differ.

Design Principles:
  - NO direct dependency on plugin DB objects (keeps layering clean).
  - Graceful failure: never crash the app if Calibre-Web internals shift.
  - All logging goes through logging_setup.get_logger().
  - Centralizes assumptions about session keys / user model attributes.

Environment / Config:
  - Session email key configurable via USERS_BOOKS_SESSION_EMAIL_KEY (handled in config).
  - Other environment handling lives in config.py.

Extensibility:
  - If future multi-tenant or group logic is needed, add discovery helpers here.
  - If upstream renames user model/attributes, only this module likely needs changes.

NOTE:
  - The dynamic imports assume standard Calibre-Web packaging. If your fork
    differs significantly, adapt `_import_user_internals()`.
"""

from __future__ import annotations

from typing import Optional, Tuple, Any
from flask import session

from . import config
from .logging_setup import get_logger

LOG = get_logger()

# ---------------------------------------------------------------------------
# Email normalization
# ---------------------------------------------------------------------------

def normalize_email(raw: Any) -> Optional[str]:
    """
    Normalize an email-like string:
      - Return None if not a string or empty after trim.
      - Lowercase the local + domain portion (simple approach).
    """
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    return cleaned or None


def get_session_email_key() -> str:
    """Return configured session key name holding the current user's email."""
    return config.session_email_key()


def get_current_user_email() -> Optional[str]:
    """
    Fetch and normalize the current user's email from the session (if present).
    This does NOT validate format—only basic normalization.
    """
    raw = session.get(get_session_email_key())
    return normalize_email(raw)


# ---------------------------------------------------------------------------
# Session-based identity & permission helpers
# ---------------------------------------------------------------------------

def get_current_user_id() -> Optional[int]:
    """
    Retrieve the current user id from Flask session.
    Returns None if not present or invalid.
    """
    uid = session.get("user_id")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None


def is_admin_user() -> bool:
    """
    Return True if the currently logged-in Calibre-Web user has the admin role.

    Fallback order:
      1. Use cps.ub.current_user (preferred; reflects actual authenticated user object).
      2. If unavailable or anonymous, fallback to session flag 'is_admin' (legacy / compatibility).
    """
    try:
        from cps import ub  # type: ignore
        cu = getattr(ub, "current_user", None)
        if cu and getattr(cu, "is_authenticated", False):
            # upstream user model exposes role_admin()
            has_role_admin = getattr(cu, "role_admin", None)
            if callable(has_role_admin):
                return bool(has_role_admin())
            # fallback: inspect 'role' bitmask directly if present
            role_val = getattr(cu, "role", None)
            if role_val is not None:
                try:
                    from cps import constants  # type: ignore
                    return bool(role_val & constants.ROLE_ADMIN)
                except Exception:
                    pass
    except Exception:
        # Silent fallback to session flag if import or attribute fails
        pass
    return bool(session.get("is_admin", False))


class PermissionError(Exception):
    """Raised when an operation requires admin privileges."""


def ensure_admin() -> None:
    """
    Raise PermissionError if the current authenticated user is not an admin.

    Uses is_admin_user() which prefers the actual Calibre-Web current_user role,
    falling back to any legacy session flag. This avoids false negatives when
    the session lacks 'is_admin' but the user object is properly authenticated.
    """
    if not is_admin_user():
        raise PermissionError("Admin privileges required")


# ---------------------------------------------------------------------------
# Calibre-Web user model dynamic discovery & lookup
# ---------------------------------------------------------------------------

def _import_user_internals() -> Tuple[Any, Any]:
    """
    Attempt to import Calibre-Web's DB session + user model.

    Return:
      (db_session_object, UserModelClass)
      or (None, None) if discovery fails.

    Strategy:
      1. Try `from cps import db`
      2. Try model name variants in cps.models:
         - User
         - Users
         - CWUser
      First successful match wins.

    This function deliberately catches broad exceptions to avoid
    breaking the entire plugin if upstream internals change.
    """
    try:
        from cps import db  # type: ignore
    except Exception as exc:
        LOG.debug("Failed importing cps.db: %s", exc)
        return None, None

    # Candidate model names to try.
    candidate_names = ("User", "Users", "CWUser")

    user_model = None
    try:
        from cps import models as cw_models  # type: ignore
        for name in candidate_names:
            user_model = getattr(cw_models, name, None)
            if user_model:
                break
    except Exception as exc:
        LOG.debug("Failed importing cps.models: %s", exc)
        user_model = None

    # Fallback: direct import path (some Calibre-Web layouts expose cps.models.User)
    if user_model is None:
        try:
            from cps.models import User as DirectUser  # type: ignore
            user_model = DirectUser
        except Exception:
            pass

    if not user_model:
        LOG.debug("Could not resolve a user model from Calibre-Web.")
        return None, None

    return db.session, user_model  # type: ignore


def resolve_user_by_email(email: str) -> Any:
    """
    Return a user ORM object matching the given normalized email, or None.

    This function:
      - Assumes email is already normalized (call normalize_email first).
      - Tries SQLAlchemy 1.x / 2.x compatible select usage.
      - Attempts common attribute names for ID retrieval at higher layers.

    Does NOT raise if lookup fails; logs at DEBUG instead.
    """
    if not email:
        return None

    db_sess, UserModel = _import_user_internals()
    if not db_sess or not UserModel:
        return None

    try:
        from sqlalchemy import select as sa_select
        stmt = sa_select(UserModel).where(UserModel.email == email)  # type: ignore[attr-defined]
        row = db_sess.execute(stmt).scalar_one_or_none()
        return row
    except Exception as exc:
        LOG.debug("resolve_user_by_email error (email=%s): %s", email, exc)
        return None


def resolve_user_id_by_email(email: str) -> Optional[int]:
    """
    Resolve and return the numeric user id for the given normalized email.
    Attempts common id attribute names: id, user_id, pk.

    Returns:
      int user id or None if not found.
    """
    user = resolve_user_by_email(email)
    if not user:
        return None

    for attr in ("id", "user_id", "pk"):
        if hasattr(user, attr):
            try:
                return int(getattr(user, attr))
            except (TypeError, ValueError):
                continue
    return None


# ---------------------------------------------------------------------------
# Public export surface
# ---------------------------------------------------------------------------

__all__ = [
    "normalize_email",
    "get_session_email_key",
    "get_current_user_email",
    "get_current_user_id",
    "is_admin_user",
    "ensure_admin",
    "PermissionError",
    "resolve_user_by_email",
    "resolve_user_id_by_email",
]
