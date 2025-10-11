"""Route & override registration.

Called from startup to register blueprints and apply any calibre-web
runtime overrides (e.g., nav injection, filter hooks).

Incremental migration: we still call into the legacy plugin init for now to
avoid breaking behavior; later we'll inline the needed pieces and delete the
plugin package.
"""
from __future__ import annotations
from typing import Any

from .admin_users_books import register_blueprint as register_admin_bp
from .admin_ebookslv import register_ebookslv_blueprint
from .admin_mozello import register_blueprints as register_mozello_bps
from .health import register_health
from app.routes.overrides.nav_injection import (
    register_loader_injection,
    register_response_injection,
)

def _ensure_nav_injection(app: Any) -> None:
    """Register both loader and response nav injection handlers."""
    try:
        register_loader_injection(app)
    except Exception:
        pass
    try:
        register_response_injection(app)
    except Exception:
        pass


def register_all(app: Any) -> None:
    # Register our admin blueprint & navigation injection.
    register_admin_bp(app)  # API + legacy redirects
    register_ebookslv_blueprint(app)  # new consolidated UI
    register_mozello_bps(app)
    register_health(app)
    _ensure_nav_injection(app)

__all__ = ["register_all"]
