"""Runtime override for Calibre-Web ISO language display names.

Goal:
- Fix LV UI where /language page shows "Unknown" for all languages because
  Calibre-Web's iso_language_names mapping does not include Latvian.
- Apply project-specific RU wording for Latvian language.

Implementation:
- Monkey-patch cps.isoLanguages.get_language_name with a wrapper that delegates
    to app.services.language_names_service.get_language_name.
- Monkey-patch cps.isoLanguages.get_language_names to ensure it never returns
    None (Calibre-Web expects a dict and calls .items() in multiple places).

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

    original_get_language_names: Callable[[object], object] | None = getattr(isoLanguages, "get_language_names", None)
    if callable(original_get_language_names):
        def _patched_get_language_names(locale: object) -> dict:
            try:
                existing = original_get_language_names(locale)
                if isinstance(existing, dict):
                    return existing
            except Exception:
                existing = None

            # Calibre-Web may return None for locales not included in its
            # iso_language_names mapping (e.g. LV). Downstream code frequently
            # expects a dict and calls `.items()`.
            locale_str = str(locale) if locale is not None else ""
            locale_lang = getattr(locale, "language", None) or (locale_str.split("_")[0].split("-")[0] if locale_str else "en")
            cache_key = (locale_str or locale_lang or "en").lower()

            cache = getattr(isoLanguages, "_ebookslv_language_names_cache", None)
            if not isinstance(cache, dict):
                cache = {}
                try:
                    setattr(isoLanguages, "_ebookslv_language_names_cache", cache)
                except Exception:
                    # Best effort cache only.
                    pass
            cached = cache.get(cache_key)
            if isinstance(cached, dict):
                return cached

            # Build a localized mapping based on Babel language display names.
            # Keys are ISO639-3 (Calibre) codes, values are localized names.
            names_map: dict = {}

            try:
                from babel import Locale as BabelLocale  # type: ignore

                babel_locale = BabelLocale.parse(locale_str or locale_lang)
            except Exception:
                babel_locale = None

            language_names_source = getattr(isoLanguages, "_LANGUAGE_NAMES", None)
            base: dict | None = None
            if isinstance(language_names_source, dict):
                base = language_names_source.get("en")
                if not isinstance(base, dict):
                    base = language_names_source.get("en_US")
                if not isinstance(base, dict) and language_names_source:
                    # Fallback: first available locale map.
                    first = next(iter(language_names_source.values()), None)
                    base = first if isinstance(first, dict) else None

            if not isinstance(base, dict):
                base = {}

            for iso639_3, english_name in base.items():
                localized = None
                if babel_locale is not None:
                    try:
                        # Convert ISO639-3 -> ISO639-1 for Babel when possible.
                        lang_obj = isoLanguages.get(part3=iso639_3)
                        iso639_1 = getattr(lang_obj, "part1", None)
                        if iso639_1:
                            localized = babel_locale.languages.get(iso639_1)
                    except Exception:
                        localized = None

                if localized:
                    names_map[iso639_3] = localized
                else:
                    names_map[iso639_3] = english_name

            # Final safety: never return an empty mapping.
            if not names_map:
                names_map = base

            try:
                cache[cache_key] = names_map
            except Exception:
                pass
            return names_map

        try:
            isoLanguages.get_language_names = _patched_get_language_names  # type: ignore[assignment]
        except Exception:
            LOG.debug("Failed to patch cps.isoLanguages.get_language_names", exc_info=True)
    else:
        LOG.debug("cps.isoLanguages.get_language_names not callable; skipping language-name map override")

    original_get_language_name: Callable[[object, object], str] | None = getattr(isoLanguages, "get_language_name", None)
    if not callable(original_get_language_name):
        LOG.debug("cps.isoLanguages.get_language_name not callable; skipping override")
        return

    def _patched_get_language_name(locale: object, lang_code: object) -> str:
        return language_names_service.get_language_name(locale, lang_code, fallback=original_get_language_name)

    try:
        isoLanguages.get_language_name = _patched_get_language_name  # type: ignore[assignment]
    except Exception:
        LOG.debug("Failed to patch cps.isoLanguages.get_language_name", exc_info=True)
        return

    setattr(app, "_ebookslv_iso_language_names_override", True)
    LOG.debug("ISO language name override registered")


__all__ = ["register_iso_language_names_override"]
