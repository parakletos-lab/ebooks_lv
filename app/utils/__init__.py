"""Utility helpers.

Bridging import surface so other code can shift from plugins.users_books.utils
without large search/replace churn.
"""
from .identity import (
    normalize_email,
    get_session_email_key,
    get_current_user_email,
    get_current_user_id,
    is_admin_user,
    ensure_admin,
    PermissionError,
)
from . import constants  # re-export module for ROLE_ADMIN access

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

