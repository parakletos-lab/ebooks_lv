"""Helpers for extending Flask-Babel translation directories."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence

from flask_babel import get_babel
from flask import session

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


__all__ = ["configure_translations", "patch_locale_selector"]
