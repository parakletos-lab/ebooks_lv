"""Shared language preference helpers for UI switching."""
from __future__ import annotations

from typing import Optional

from app.services import calibre_users_service

SESSION_LOCALE_KEY = "ub_preferred_locale"
SUPPORTED_LANGUAGES = ("lv", "ru", "en")


def normalize_language_choice(raw: Optional[str]) -> Optional[str]:
    """Normalize a user-provided language code to a supported value."""
    try:
        return calibre_users_service._normalize_language_preference(raw)  # type: ignore[attr-defined]
    except Exception:
        return None


__all__ = [
    "SESSION_LOCALE_KEY",
    "SUPPORTED_LANGUAGES",
    "normalize_language_choice",
]
