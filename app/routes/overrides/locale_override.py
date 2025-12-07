"""Locale selector override honoring session language choice."""
from __future__ import annotations

from flask import session

from app.i18n.preferences import SESSION_LOCALE_KEY, normalize_language_choice
from app.utils.identity import get_current_user_id
from app.utils.logging import get_logger

try:  # pragma: no cover - runtime dependency
    from cps.cw_babel import babel, get_locale as _cw_get_locale  # type: ignore
except Exception:  # pragma: no cover
    babel = None  # type: ignore

    def _cw_get_locale():  # type: ignore
        return None

LOG = get_logger("locale_override")
DEFAULT_LOCALE = "lv"


def _session_locale() -> str | None:
    raw = session.get(SESSION_LOCALE_KEY)
    if isinstance(raw, str):
        return normalize_language_choice(raw)
    return None


def _select_locale():
    session_locale = _session_locale()
    if session_locale:
        return session_locale

    user_id = None
    try:
        user_id = get_current_user_id()
    except Exception:  # pragma: no cover - defensive
        user_id = None

    if user_id:
        try:
            return _cw_get_locale() or DEFAULT_LOCALE
        except Exception:  # pragma: no cover - defensive
            return DEFAULT_LOCALE

    try:
        session[SESSION_LOCALE_KEY] = DEFAULT_LOCALE
        session.modified = True
    except Exception:  # pragma: no cover - defensive
        pass
    return DEFAULT_LOCALE


def register_locale_override(app):  # pragma: no cover - glue code
    if getattr(app, "_users_books_locale_override", False):  # type: ignore[attr-defined]
        return
    if babel is None:
        LOG.debug("Flask-Babel unavailable; locale override skipped")
        return
    try:
        if hasattr(babel, "localeselector"):
            babel.localeselector(_select_locale)  # type: ignore[attr-defined]
        else:
            babel.init_app(app, locale_selector=_select_locale)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover
        LOG.debug("Failed to register locale selector override: %s", exc)
        return
    setattr(app, "_users_books_locale_override", True)
    LOG.debug("Locale selector override registered")


__all__ = ["register_locale_override", "SESSION_LOCALE_KEY"]
