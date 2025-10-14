"""Application initialization / wiring.

Orchestrates: DB init, route registration, template path adjustments (later),
legacy plugin bridging.
"""
from __future__ import annotations
from typing import Any

from app.db import init_engine_once
from app.db.models import MozelloConfig  # ensure model imported so metadata includes table
from app.routes.inject import register_all as register_routes
from app.routes.admin_mozello import register_blueprints as register_mozello
from app.config import mozello_api_key
from app.services import mozello_service
from flask import Blueprint
import os
import logging
try:
    from flask import send_from_directory, abort
except Exception:  # pragma: no cover
    send_from_directory = None  # type: ignore
    abort = None  # type: ignore


log = logging.getLogger("app.startup")


def _prepend_template_path(app):
    """Ensure app/templates is before upstream templates for overrides.

    Adds a blueprint purely to insert a loader search path early.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app_root = os.path.abspath(os.path.join(base_dir, ".."))
    override_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")
    static_rel = os.path.relpath(static_dir, app_root)
    if not os.path.isdir(override_dir):
        return
    # Use a dummy blueprint with template_folder pointing to override_dir (and static for custom assets)
    if not getattr(app, '_app_templates_bp', None):
        # Use absolute path for static_folder so Flask can serve files from
        # our override static directory regardless of import root.
        bp = Blueprint('_app_templates', __name__, template_folder=override_dir, static_folder=static_dir, static_url_path='/app_static')
        app.register_blueprint(bp)
        setattr(app, '_app_templates_bp', bp)
        log.debug("Registered _app_templates blueprint for override dir %s, static %s", override_dir, static_rel)


def init_app(app: Any) -> None:
    log.debug("init_app starting")
    init_engine_once()
    log.debug("DB engine initialized")
    register_routes(app)
    register_mozello(app)
    log.debug("Routes registered (users_books + mozello)")
    # Our custom assets are exposed via the _app_templates blueprint's
    # static folder. Templates should reference them with
    # url_for('_app_templates.static', filename='<name>').
    # We intentionally do not copy files into the global app.static_folder
    # or register duplicate /static/ routes to avoid confusing overlaps.
    
    # Bootstrap Mozello API key from env if present and not already stored.
    try:
        env_key = mozello_api_key()
        if env_key:
            current = mozello_service._get_api_key_raw()  # type: ignore[attr-defined]
            if not current:
                mozello_service.update_settings(env_key, None, None)
                log.info("Mozello API key seeded from environment.")
            else:
                log.debug("Mozello API key already present; env value ignored.")
    except Exception:
        log.exception("Failed seeding Mozello API key from environment")
    _prepend_template_path(app)
    # Register detail injection (loader + response fallback) defensively.
    try:
        from app.routes.overrides import detail_injection
        detail_injection.register_loader_injection(app)
        detail_injection.register_response_injection(app)
        log.debug('Registered detail_injection overrides')
    except Exception:
        log.exception('Failed to register detail_injection overrides')

    log.info("App startup wiring complete (legacy plugin still active).")

__all__ = ["init_app"]
