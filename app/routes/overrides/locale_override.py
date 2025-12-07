"""Locale selector override honoring session language choice."""
from __future__ import annotations

from flask import session

from app.i18n.preferences import SESSION_LOCALE_KEY, normalize_language_choice
from app.utils.logging import get_logger

try:  # pragma: no cover - runtime dependency
    from cps.cw_babel import babel, get_locale as _cw_get_locale  # type: ignore
except Exception:  # pragma: no cover
    babel = None  # type: ignore

    def _cw_get_locale():  # type: ignore
        return None

LOG = get_logger("locale_override")


def _session_locale() -> str | None:
    raw = session.get(SESSION_LOCALE_KEY)
    if isinstance(raw, str):
        return normalize_language_choice(raw)
    return None


def _select_locale():
    session_locale = _session_locale()
    if session_locale:
        return session_locale
    try:
        return _cw_get_locale()
    except Exception:  # pragma: no cover - defensive
        return None


def register_locale_override(app):  # pragma: no cover - glue code
    if getattr(app, "_users_books_locale_override", False):  # type: ignore[attr-defined]
        return
    if babel is None:
        LOG.debug("Flask-Babel unavailable; locale override skipped")
        return
    try:
        babel.localeselector(_select_locale)  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover
        LOG.debug("Failed to register locale selector override: %s", exc)
        return
    setattr(app, "_users_books_locale_override", True)
    LOG.debug("Locale selector override registered")


__all__ = ["register_locale_override", "SESSION_LOCALE_KEY"]
