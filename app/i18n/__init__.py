"""Helpers for extending Flask-Babel translation directories."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable, List, Sequence

from flask_babel import get_babel
from flask import session
from flask_babel import gettext

from app.utils.logging import get_logger
from app.i18n.preferences import SESSION_LOCALE_KEY, normalize_language_choice

LOG = get_logger("i18n")

_APP_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _APP_ROOT.parent
_DEFAULT_TRANSLATION_ROOTS: Sequence[Path] = (
    _REPO_ROOT / "translations" / "calibre-web",
    _REPO_ROOT / "translations" / "ebookslv",
)


def _normalize_paths(paths: Iterable[Path | str]) -> List[str]:
    seen: List[str] = []
    for candidate in paths:
        path = Path(candidate).resolve()
        if not path.is_dir():
            LOG.debug("Translation directory missing; skipping: %s", path)
            continue
        as_str = str(path)
        if as_str not in seen:
            seen.append(as_str)
    return seen


def configure_translations(app, extra_roots: Iterable[Path | str] | None = None) -> None:
    """Register first-party translation directories in Babel's search path.

    Note: Flask-Babel's translation directory handling is order-sensitive.
    To ensure our overrides win, we place our translation roots *first*.
    """
    try:
        babel_cfg = get_babel(app)
    except Exception:  # pragma: no cover - defensive guard
        LOG.warning("Flask-Babel not initialized; skipping translation configuration")
        return

    candidates: List[Path | str] = list(_DEFAULT_TRANSLATION_ROOTS)
    if extra_roots:
        candidates.extend(extra_roots)

    desired = _normalize_paths(candidates)
    existing = list(getattr(babel_cfg, "translation_directories", []))

    # Prepend our desired roots, keeping stable order, and preserving any
    # pre-existing translation directories after them.
    merged: List[str] = []
    for directory in desired:
        if directory not in merged:
            merged.append(directory)
    for directory in existing:
        if directory not in merged:
            merged.append(directory)

    if merged == existing:
        return

    babel_cfg.translation_directories = merged
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = ";".join(merged)
    LOG.info("Registered %s custom translation directories", len(desired))


def patch_locale_selector(app) -> None:
    """Prefer `ub_preferred_locale` for anonymous users.

    Calibre-Web's upstream locale selector uses the logged-in user's locale or
    the browser's Accept-Language header. For our login/token flows we want the
    UI language to follow our session preference (and the token user locale we
    store in-session).
    """

    try:  # runtime dependency on Calibre-Web
        from cps.cw_babel import babel as cw_babel, get_locale as cw_get_locale  # type: ignore
    except Exception:  # pragma: no cover
        return

    def _wrapped_get_locale():
        preferred = normalize_language_choice(session.get(SESSION_LOCALE_KEY))
        if preferred:
            return preferred
        return cw_get_locale()

    try:
        cw_babel.locale_selector_func = _wrapped_get_locale  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        return

    try:
        babel_cfg = get_babel(app)
        babel_cfg.locale_selector_func = _wrapped_get_locale  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass


def patch_anonymous_user_locale(app) -> None:
    """Make `current_user.locale` follow session locale for anonymous visitors.

    Calibre-Web's templates use `current_user.locale` to decide which JS locale
    packs to load (bootstrap-select, bootstrap-datepicker).

    For anonymous visitors, `current_user` is an instance of `cps.ub.Anonymous`
    whose `.locale` is loaded from the anonymous/guest DB row, which is often
    `en`. That causes locale JS packs to be skipped even when our session locale
    selector (see `patch_locale_selector`) is set to LV/RU.

    We patch `Anonymous.loadSettings()` to overwrite `.locale` from our session
    preference when present.
    """

    if getattr(app, "_ebookslv_anonymous_locale_patched", False):
        return

    try:  # runtime dependency on Calibre-Web
        from cps import ub as cw_ub  # type: ignore
    except Exception:  # pragma: no cover
        return

    anonymous_cls = getattr(cw_ub, "Anonymous", None)
    if anonymous_cls is None:
        return

    if getattr(anonymous_cls, "_ebookslv_locale_patch", False):
        setattr(app, "_ebookslv_anonymous_locale_patched", True)
        return

    original = getattr(anonymous_cls, "loadSettings", None)
    if not callable(original):
        return

    def _wrapped_load_settings(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        preferred = normalize_language_choice(session.get(SESSION_LOCALE_KEY))
        if preferred:
            try:
                self.locale = preferred
            except Exception:
                pass
        return result

    try:
        anonymous_cls.loadSettings = _wrapped_load_settings  # type: ignore[assignment]
        setattr(anonymous_cls, "_ebookslv_locale_patch", True)
    except Exception:  # pragma: no cover
        return

    setattr(app, "_ebookslv_anonymous_locale_patched", True)


def patch_template_context_i18n(app) -> None:
    """Patch Calibre-Web advanced search i18n without overriding templates.

    Calibre-Web renders custom column labels on `/advsearch` using `c.name` directly.
    We translate those names in the Python layer before the template is rendered.
    This avoids copying upstream templates into `app/templates/`.
    """

    if getattr(app, "_ebookslv_template_i18n_patched", False):
        return

    def _translate_custom_column_name(obj) -> None:
        try:
            name = getattr(obj, "name")
            if isinstance(name, str) and name:
                setattr(obj, "name", gettext(name))
        except Exception:
            try:
                name = obj.get("name")  # type: ignore[attr-defined]
                if isinstance(name, str) and name:
                    obj["name"] = gettext(name)  # type: ignore[index]
            except Exception:
                return

    # Runtime patch: wrap Calibre-Web search form preparation to translate cc names.
    try:
        import cps.search as cw_search  # type: ignore
    except Exception:
        return

    if getattr(cw_search, "_ebookslv_cc_name_patch", False):
        setattr(app, "_ebookslv_template_i18n_patched", True)
        return

    original = getattr(cw_search, "render_prepare_search_form", None)
    if not callable(original):
        return

    def _wrapped_render_prepare_search_form(cc):
        try:
            if cc:
                for col in cc:
                    _translate_custom_column_name(col)
        except Exception:
            pass
        return original(cc)

    try:
        cw_search.render_prepare_search_form = _wrapped_render_prepare_search_form  # type: ignore[assignment]
        setattr(cw_search, "_ebookslv_cc_name_patch", True)
    except Exception:
        return
    setattr(app, "_ebookslv_template_i18n_patched", True)

    # Also patch the advanced-search results header (`adv_searchterm`) to translate
    # custom column names like "Price" without mutating ORM objects.
    #
    # Important: `cps.search` imports `render_title_template` directly, so patching
    # `cps.render_template.render_title_template` is not sufficient.
    try:
        from cps import calibre_db as cw_calibre_db, config as cw_config  # type: ignore
    except Exception:
        return

    if getattr(cw_search, "_ebookslv_advsearch_term_patch", False):
        return

    original_render_title_template = getattr(cw_search, "render_title_template", None)
    if not callable(original_render_title_template):
        return

    def _translate_adv_searchterm(value: str) -> str:
        try:
            cc_cols = cw_calibre_db.get_cc_columns(cw_config, filter_config_custom_read=True)
        except Exception:
            return value

        translated = value

        # Translate non-gettexted field labels that Calibre-Web may embed
        # directly into the human-readable `adv_searchterm` string.
        translated = re.sub(
            r"(?<!\w)" + re.escape("Read Status") + r"(?!\w)",
            gettext("Read Status"),
            translated,
        )

        # Translate boolean values rendered as strings (e.g. "'False'") into
        # localized Yes/No values.
        yes_localized = gettext("Yes")
        no_localized = gettext("No")
        if yes_localized == "Yes" or no_localized == "No":
            preferred = normalize_language_choice(session.get(SESSION_LOCALE_KEY))
            if preferred and preferred.startswith("ru"):
                yes_localized, no_localized = "Да", "Нет"
            elif preferred and preferred.startswith("lv"):
                yes_localized, no_localized = "Jā", "Nē"

        def _bool_repl(match: re.Match[str]) -> str:
            token = match.group(0)
            bool_value = match.group(2)
            replacement = yes_localized if bool_value == "True" else no_localized
            if token.startswith("'") and token.endswith("'"):
                return f"'{replacement}'"
            if token.startswith('"') and token.endswith('"'):
                return f'"{replacement}"'
            return replacement

        translated = re.sub(r"(?<!\w)(['\"]?)(True|False)\1(?!\w)", _bool_repl, translated)

        for col in cc_cols or []:
            try:
                raw_name = getattr(col, "name", None)
            except Exception:
                raw_name = None
            if not isinstance(raw_name, str) or not raw_name:
                continue
            localized = gettext(raw_name)
            if not localized or localized == raw_name:
                continue
            # Replace whole-token occurrences to avoid accidental partial matches.
            translated = re.sub(r"(?<!\w)" + re.escape(raw_name) + r"(?!\w)", localized, translated)
        return translated

    def _wrapped_render_title_template(*args, **kwargs):
        # Only touch advanced search pages.
        if kwargs.get("page") == "advsearch" and "adv_searchterm" in kwargs:
            term = kwargs.get("adv_searchterm")
            if isinstance(term, str) and term:
                kwargs["adv_searchterm"] = _translate_adv_searchterm(term)
        return original_render_title_template(*args, **kwargs)

    try:
        cw_search.render_title_template = _wrapped_render_title_template  # type: ignore[assignment]
        setattr(cw_search, "_ebookslv_advsearch_term_patch", True)
    except Exception:
        return


__all__ = [
    "configure_translations",
    "patch_locale_selector",
    "patch_anonymous_user_locale",
    "patch_template_context_i18n",
]
