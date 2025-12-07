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
from app.i18n import configure_translations
from flask import Blueprint
import os
import logging
log = logging.getLogger("app.startup")


def _prepend_template_path(app):
    """Ensure app/templates is before upstream templates for overrides.

    Adds a blueprint purely to insert a loader search path early.
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    override_dir = os.path.join(base_dir, "templates")
    repo_root = os.path.abspath(os.path.join(base_dir, ".."))
    static_dir = os.path.join(base_dir, "static")
    if not os.path.isdir(override_dir):
        return
    # Use a dummy blueprint with template_folder pointing to override_dir (and static for custom assets)
    if not getattr(app, '_app_templates_bp', None):
        bp = Blueprint(
            '_app_templates',
            __name__,
            template_folder=override_dir,
            static_folder=static_dir,
            static_url_path='/app_static'
        )
        app.register_blueprint(bp)
        setattr(app, '_app_templates_bp', bp)
        log.debug(
            "Registered _app_templates blueprint for override dir %s with static /app_static (%s)",
            override_dir,
            static_dir,
        )
    # Ensure override path is first in the Jinja search path
    loader = getattr(app, 'jinja_loader', None)
    searchpath = getattr(loader, 'searchpath', None)
    if isinstance(searchpath, list):
        if override_dir not in searchpath:
            searchpath.insert(0, override_dir)
            log.debug("Prepended override dir to jinja searchpath: %s", override_dir)
        if repo_root not in searchpath:
            searchpath.append(repo_root)
            log.debug("Appended repo root to jinja searchpath: %s", repo_root)


def init_app(app: Any) -> None:
    log.debug("init_app starting")
    init_engine_once()
    log.debug("DB engine initialized")
    register_routes(app)
    register_mozello(app)
    log.debug("Routes registered (users_books + mozello)")
    # Bootstrap Mozello API key from environment if present and DB empty
    try:
        env_key = mozello_api_key()
        if env_key:
            current = mozello_service._get_api_key_raw()  # type: ignore[attr-defined]
            if not current:
                mozello_service.update_settings(env_key, None, None)
                log.info("Mozello API key seeded from environment.")
            else:
                log.debug("Mozello API key already stored; environment value ignored.")
    except Exception:
        log.exception("Failed seeding Mozello API key from environment")
    _prepend_template_path(app)
    configure_translations(app)
    log.info("App startup wiring complete (legacy plugin still active).")

__all__ = ["init_app"]
