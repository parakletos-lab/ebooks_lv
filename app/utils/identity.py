"""Identity & permission helpers migrated from plugin utils (subset)."""
from __future__ import annotations
from typing import Optional, Any
from flask import session

from app import config as app_config
from app.utils import constants  # ensure constants module import side-effect for ROLE_ADMIN (used by other modules)


def normalize_email(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    return cleaned or None


def get_session_email_key() -> str:
    return app_config.session_email_key()


def _cw_current_user():
    try:
        from cps.cw_login import current_user as login_current_user  # type: ignore
        return login_current_user
    except Exception:
        return None


def _ub_current_user():
    try:
        from cps import ub as cw_ub  # type: ignore
        return getattr(cw_ub, "current_user", None)
    except Exception:
        return None


def get_current_user_email() -> Optional[str]:
    raw = session.get(get_session_email_key())
    email = normalize_email(raw)
    if email:
        return email

    current = _cw_current_user()
    try:
        candidate = getattr(current, "email", None)
        email = normalize_email(candidate)
        if email:
            return email
    except Exception:
        pass

    ub_user = _ub_current_user()
    try:
        candidate = getattr(ub_user, "email", None)
        email = normalize_email(candidate)
        if email:
            return email
    except Exception:
        pass

    return None


def get_current_user_id() -> Optional[int]:
    uid = session.get("user_id")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        pass

    current = _cw_current_user()
    try:
        candidate = getattr(current, "id", None)
        if candidate is not None:
            return int(candidate)
    except Exception:
        pass

    ub_user = _ub_current_user()
    try:
        candidate = getattr(ub_user, "id", None)
        if candidate is not None:
            return int(candidate)
    except Exception:
        pass

    return None


def is_admin_user() -> bool:  # simplified migration copy
    try:
        current = _cw_current_user()
        if current and getattr(current, "is_authenticated", False):
            has_role_admin = getattr(current, "role_admin", None)
            if callable(has_role_admin):
                return bool(has_role_admin())
            role_attr = getattr(current, "role", None)
            if role_attr is not None:
                try:
                    from cps import constants as cw_consts  # type: ignore
                    return bool(int(role_attr) & int(getattr(cw_consts, "ROLE_ADMIN", 1)))
                except Exception:
                    pass
    except Exception:
        pass

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
    "constants",
]
