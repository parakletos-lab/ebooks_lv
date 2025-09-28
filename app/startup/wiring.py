"""Application initialization / wiring.

Orchestrates: DB init, route registration, template path adjustments (later),
legacy plugin bridging.
"""
from __future__ import annotations
from typing import Any

from app.db import init_engine_once
from app.routes.inject import register_all as register_routes
from flask import Blueprint
import os


def _prepend_template_path(app):
    """Ensure app/templates is before upstream templates for overrides.

    Adds a blueprint purely to insert a loader search path early.
    """
    override_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "templates"))
    if not os.path.isdir(override_dir):
        return
    # Use a dummy blueprint with template_folder pointing to override_dir
    if not getattr(app, '_app_templates_bp', None):
        bp = Blueprint('_app_templates', __name__, template_folder=override_dir)
        app.register_blueprint(bp)
        setattr(app, '_app_templates_bp', bp)
from app.utils.logging import get_logger


def init_app(app: Any) -> None:
    log = get_logger("app.startup")
    init_engine_once()
    register_routes(app)
    _prepend_template_path(app)
    log.info("App startup wiring complete (legacy plugin still active).")

__all__ = ["init_app"]
