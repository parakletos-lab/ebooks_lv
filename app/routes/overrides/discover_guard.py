"""Disable the Discover (Random Books) view for anonymous users.

We intentionally do NOT modify core calibre-web routes/templates on disk.
Instead, we wrap the existing view function to redirect anonymous traffic
away from discover while keeping the feature available for authenticated users.
"""
from __future__ import annotations

from flask import redirect, url_for

from app.utils.identity import get_current_user_id, is_admin_user
from app.utils.logging import get_logger

LOG = get_logger("discover_guard")


def register_discover_guard(app):  # pragma: no cover - glue code
    if getattr(app, "_ebookslv_discover_guard", False):  # type: ignore[attr-defined]
        return

    view = app.view_functions.get("web.books_list")
    if not view:
        LOG.debug("web.books_list view missing; guard skipped")
        return

    def _guarded_books_list(data, *args, **kwargs):
        try:
            is_authenticated = get_current_user_id() is not None
        except Exception:
            is_authenticated = False

        if data == "discover" and not (is_authenticated or is_admin_user()):
            LOG.info("Discover blocked for anonymous user")
            try:
                return redirect(url_for("web.index"))
            except Exception:  # pragma: no cover - fallback
                return redirect("/")

        return view(data, *args, **kwargs)

    app.view_functions["web.books_list"] = _guarded_books_list
    setattr(app, "_ebookslv_discover_guard", True)
    LOG.debug("Discover guard registered")


__all__ = ["register_discover_guard"]
