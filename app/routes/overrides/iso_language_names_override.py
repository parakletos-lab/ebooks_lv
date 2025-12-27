"""Runtime override for Calibre-Web ISO language display names.

Goal:
- Fix LV UI where /language page shows "Unknown" for all languages because
  Calibre-Web's iso_language_names mapping does not include Latvian.
- Apply project-specific RU wording for Latvian language.

Implementation:
- Monkey-patch cps.isoLanguages.get_language_name with a wrapper that delegates
  to app.services.language_names_service.get_language_name.

This avoids editing the vendored /calibre-web codebase.
"""

from __future__ import annotations

from typing import Any, Callable

from app.services import language_names_service
from app.utils.logging import get_logger

LOG = get_logger("iso_language_names_override")


def register_iso_language_names_override(app: Any) -> None:
    if getattr(app, "_ebookslv_iso_language_names_override", False):  # type: ignore[attr-defined]
        return

    try:
        from cps import isoLanguages  # type: ignore
    except Exception:
        LOG.debug("cps.isoLanguages unavailable; skipping override")
        return

    original: Callable[[object, object], str] | None = getattr(isoLanguages, "get_language_name", None)
    if not callable(original):
        LOG.debug("cps.isoLanguages.get_language_name not callable; skipping override")
        return

    def _patched_get_language_name(locale: object, lang_code: object) -> str:
        return language_names_service.get_language_name(locale, lang_code, fallback=original)

    try:
        isoLanguages.get_language_name = _patched_get_language_name  # type: ignore[assignment]
    except Exception:
        LOG.debug("Failed to patch cps.isoLanguages.get_language_name", exc_info=True)
        return

    setattr(app, "_ebookslv_iso_language_names_override", True)
    LOG.debug("ISO language name override registered")


__all__ = ["register_iso_language_names_override"]
