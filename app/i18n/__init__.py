"""Helpers for extending Flask-Babel translation directories."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence

from flask_babel import get_babel

from app.utils.logging import get_logger

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
    """Append first-party translation directories to Babel's search path."""
    try:
        babel_cfg = get_babel(app)
    except Exception:  # pragma: no cover - defensive guard
        LOG.warning("Flask-Babel not initialized; skipping translation configuration")
        return

    candidates: List[Path | str] = list(_DEFAULT_TRANSLATION_ROOTS)
    if extra_roots:
        candidates.extend(extra_roots)

    desired = _normalize_paths(candidates)
    current = list(getattr(babel_cfg, "translation_directories", []))
    appended: List[str] = []
    for directory in desired:
        if directory not in current:
            current.append(directory)
            appended.append(directory)

    if not appended:
        return

    babel_cfg.translation_directories = current
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = ";".join(current)
    LOG.info("Registered %s custom translation directories", len(appended))


__all__ = ["configure_translations"]
