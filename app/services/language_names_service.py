"""Language name display helpers.

Calibre-Web uses cps.isoLanguages.get_language_name(locale, lang_code) which relies on
an internal locale->language-name map. Some UI locales (notably Latvian) are not
present in that map which causes the UI to render "Unknown" for all languages.

This service provides a robust lookup:
- Prefer Babel/CLDR localized language names when available.
- Convert ISO639-2 (3-letter) codes to ISO639-1 (2-letter) when possible.
- Fall back to Calibre-Web's built-in ISO language names (typically English).
- Apply project-specific wording overrides (e.g. RU "Латышский").

This is read-only and safe to call during template rendering.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.utils.logging import get_logger

LOG = get_logger("language_names_service")

UNKNOWN_TRANSLATION = "Unknown"


def _normalize_locale(locale: object) -> str:
    raw = str(locale or "").strip()
    if not raw:
        return ""
    return raw.replace("-", "_")


def _normalize_lang_code(lang_code: object) -> str:
    raw = str(lang_code or "").strip().lower()
    return raw


def _locale_language(locale_str: str) -> str:
    if not locale_str:
        return ""
    return locale_str.split("_", 1)[0].lower()


def _iso639_3_to_1(code: str) -> Optional[str]:
    # Calibre language codes are typically ISO639-2/T (3-letter).
    if not code or len(code) != 3:
        return None
    try:
        from cps import isoLanguages  # type: ignore

        lang = isoLanguages.get(part3=code)
        part1 = getattr(lang, "part1", None)
        if part1:
            part1_str = str(part1).strip().lower()
            if part1_str and len(part1_str) == 2:
                return part1_str
    except Exception:
        return None
    return None


def _babel_language_name(locale_str: str, code: str) -> Optional[str]:
    try:
        from babel import Locale  # type: ignore

        loc = Locale.parse(locale_str or "en")
        # Prefer part1 where possible, but also try raw code.
        candidates = []
        part1 = _iso639_3_to_1(code)
        if part1:
            candidates.append(part1)
        candidates.append(code)
        for cand in candidates:
            name = loc.languages.get(cand)
            if name:
                return str(name)
    except Exception:
        return None
    return None


def _capitalize_display_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return name
    return name[0].upper() + name[1:]


def get_language_name(
    locale: object,
    lang_code: object,
    *,
    fallback: Optional[Callable[[object, object], str]] = None,
) -> str:
    """Return localized display name for an ISO language code.

    `fallback` should typically be the original Calibre-Web resolver.
    """

    locale_str = _normalize_locale(locale)
    locale_lang = _locale_language(locale_str)
    code = _normalize_lang_code(lang_code)

    if not code:
        return UNKNOWN_TRANSLATION

    # Project-specific wording override.
    if locale_lang == "ru" and code in {"lv", "lav", "lat"}:
        return "Латышский"

    # Prefer CLDR/Babel names when available. This fixes LV locale where
    # Calibre-Web's iso_language_names map is missing.
    babel_name = _babel_language_name(locale_str, code)
    if babel_name and babel_name != UNKNOWN_TRANSLATION:
        return _capitalize_display_name(babel_name)

    # Fall back to Calibre-Web's resolver. If the current locale is missing from
    # Calibre-Web maps, force English so we don't show "Unknown" everywhere.
    if fallback is not None:
        try:
            if locale_lang and locale_lang not in {"en", "de", "fr", "es", "ru", "it", "pt", "nl", "cs", "pl", "tr", "uk", "ar", "zh", "ja", "ko"}:
                return fallback("en", code)
            return fallback(locale_str or "en", code)
        except Exception:
            LOG.debug("Fallback language name lookup failed", exc_info=True)

    return UNKNOWN_TRANSLATION


__all__ = ["get_language_name", "UNKNOWN_TRANSLATION"]
