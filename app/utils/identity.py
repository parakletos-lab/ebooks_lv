"""Identity & permission helpers migrated from plugin utils (subset)."""
from __future__ import annotations
from typing import Optional, Any
from flask import session

from app import config as app_config


def normalize_email(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    return cleaned or None


def get_session_email_key() -> str:
    return app_config.session_email_key()


def get_current_user_email() -> Optional[str]:
    raw = session.get(get_session_email_key())
    return normalize_email(raw)


def get_current_user_id() -> Optional[int]:
    uid = session.get("user_id")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None


def is_admin_user() -> bool:  # simplified migration copy
    try:
        from cps import ub  # type: ignore
        cu = getattr(ub, "current_user", None)
        if cu and getattr(cu, "is_authenticated", False):
            has_role_admin = getattr(cu, "role_admin", None)
            if callable(has_role_admin):
                return bool(has_role_admin())
    except Exception:
        pass
    return bool(session.get("is_admin", False))


class PermissionError(Exception):
    pass


def ensure_admin() -> None:
    if not is_admin_user():
        raise PermissionError("Admin privileges required")


__all__ = [
    "normalize_email",
    "get_session_email_key",
    "get_current_user_email",
    "get_current_user_id",
    "is_admin_user",
    "ensure_admin",
    "PermissionError",
]
