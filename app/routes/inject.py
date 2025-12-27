"""Route & override registration.

Called from startup to register blueprints and apply any calibre-web
runtime overrides (e.g., nav injection, filter hooks).

Incremental migration: we still call into the legacy plugin init for now to
avoid breaking behavior; later we'll inline the needed pieces and delete the
plugin package.
"""
from __future__ import annotations
from typing import Any

from .admin_ebookslv import register_ebookslv_blueprint
from .admin_mozello import register_blueprints as register_mozello_bps
from .health import register_health
from .login_override import register_login_override
from .language_switch import register_language_switch
from app.routes.overrides.nav_injection import (
    register_loader_injection,
    register_response_injection,
)
from app.routes.overrides.catalog_access import register_catalog_access
from app.routes.overrides.calibre_overrides import register_calibre_overrides
from app.routes.overrides.stats_notice import register_stats_notice
from app.routes.overrides.locale_override import register_locale_override
from app.routes.overrides.language_switch_injection import register_language_switch_injection
from app.routes.overrides.advsearch_rating_injection import register_advsearch_rating_injection
from app.routes.overrides.iso_language_names_override import register_iso_language_names_override
from app.routes.overrides.profile_guard import register_profile_guard
from app.routes.overrides.discover_guard import register_discover_guard
from app.routes.overrides.mozello_sync_injection import register_mozello_sync_injection
from app.routes.overrides.mozello_theme_injection import register_mozello_theme_injection
from app.routes.overrides.mz_pictures_gallery_injection import register_mz_pictures_gallery_injection
from app.routes.overrides.mozello_csp_img_src_injection import register_mozello_csp_img_src_injection

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
    register_login_override(app)
    register_language_switch(app)
    register_ebookslv_blueprint(app)  # new consolidated UI
    register_mozello_bps(app)
    register_health(app)
    register_catalog_access(app)
    register_stats_notice(app)
    register_calibre_overrides(app)
    register_profile_guard(app)
    register_discover_guard(app)
    register_locale_override(app)
    register_iso_language_names_override(app)
    register_language_switch_injection(app)
    register_mozello_sync_injection(app)
    register_mozello_theme_injection(app)
    register_mozello_csp_img_src_injection(app)
    register_mz_pictures_gallery_injection(app)
    register_advsearch_rating_injection(app)
    _ensure_nav_injection(app)

__all__ = ["register_all"]
