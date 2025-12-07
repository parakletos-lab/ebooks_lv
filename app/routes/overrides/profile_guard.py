"""Block /me profile access for non-admin users."""
from __future__ import annotations

from flask import redirect, url_for

from app.utils.identity import is_admin_user
from app.utils.logging import get_logger

LOG = get_logger("profile_guard")


def register_profile_guard(app):  # pragma: no cover - glue code
    if getattr(app, "_users_books_profile_guard", False):  # type: ignore[attr-defined]
        return
    view = app.view_functions.get("web.profile")
    if not view:
        LOG.debug("web.profile view missing; guard skipped")
        return

    def _guarded_profile(*args, **kwargs):
        if is_admin_user():
            return view(*args, **kwargs)
        LOG.info("Profile page blocked for non-admin user")
        try:
            return redirect(url_for("web.index"))
        except Exception:  # pragma: no cover - fallback
            return redirect("/")

    app.view_functions["web.profile"] = _guarded_profile
    setattr(app, "_users_books_profile_guard", True)
    LOG.debug("Profile guard registered")


__all__ = ["register_profile_guard"]
