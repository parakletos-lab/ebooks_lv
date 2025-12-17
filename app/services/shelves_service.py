"""Bookshelf helpers.

Currently used to ensure a per-user Wishlist shelf exists after Mozello webhook
user creation.
"""

from __future__ import annotations

from typing import Dict, Optional

from app.utils.logging import get_logger

LOG = get_logger("shelves_service")

try:  # runtime dependency on embedded Calibre-Web modules
    from cps import ub  # type: ignore
except Exception:  # pragma: no cover - running outside Calibre-Web runtime
    ub = None  # type: ignore

try:
    from flask_babel import force_locale, gettext as _  # type: ignore
except Exception:  # pragma: no cover - unit tests / minimal runtime
    force_locale = None  # type: ignore

    def _(text: str) -> str:  # type: ignore
        return text


class CalibreUnavailableError(RuntimeError):
    """Raised when Calibre-Web runtime resources are not available."""


def _ensure_runtime() -> None:
    if ub is None or getattr(ub, "session", None) is None:
        raise CalibreUnavailableError("Calibre-Web session not available")


def _session():
    return getattr(ub, "session", None)


def _normalize_locale(value: Optional[str]) -> str:
    raw = (value or "").strip().lower()
    if raw.startswith("lv"):
        return "lv"
    if raw.startswith("ru"):
        return "ru"
    return "en"


def _wishlist_name_for_locale(locale: str) -> str:
    normalized = _normalize_locale(locale)

    if force_locale:
        try:
            with force_locale(normalized):
                return _("Wishlist")
        except Exception:  # pragma: no cover - defensive
            pass

    # Fallback if Flask-Babel isn't available.
    if normalized == "lv":
        return "Vēlmju saraksts"
    if normalized == "ru":
        return "Список желаний"
    return "Wishlist"


def ensure_wishlist_shelf_for_user(
    user_id: int,
    *,
    user_locale: Optional[str] = None,
) -> Dict[str, object]:
    """Ensure an idempotent Wishlist shelf exists for the given user."""
    _ensure_runtime()

    sess = _session()
    if not sess:
        raise CalibreUnavailableError("Calibre session unavailable")

    locale = user_locale
    if not locale:
        user = sess.query(ub.User).filter(ub.User.id == int(user_id)).one_or_none()
        locale = getattr(user, "locale", None) if user else None

    shelf_name = _wishlist_name_for_locale(locale)

    existing = (
        sess.query(ub.Shelf)
        .filter(ub.Shelf.user_id == int(user_id))
        .filter(ub.Shelf.name == shelf_name)
        .one_or_none()
    )
    if existing:
        return {"status": "existing", "shelf_id": existing.id, "name": existing.name}

    shelf = ub.Shelf()
    shelf.user_id = int(user_id)
    shelf.name = shelf_name
    shelf.is_public = 0

    sess.add(shelf)
    try:
        sess.commit()
    except Exception as exc:  # pragma: no cover - SQL error path
        sess.rollback()
        LOG.warning("Failed creating wishlist shelf user_id=%s error=%s", user_id, exc)
        raise

    return {"status": "created", "shelf_id": shelf.id, "name": shelf.name}


__all__ = [
    "CalibreUnavailableError",
    "ensure_wishlist_shelf_for_user",
]
