"""
users_books.api
================

Blueprint assembly for the users_books plugin.

This module centralizes the creation and registration of the Flask Blueprint
used for all plugin HTTP routes (user endpoints, admin endpoints, metrics,
webhook, health, etc.).

Design Goals:
  - Lazy import of route modules to avoid circular dependencies
    (services -> db -> config, etc.).
  - Single public function `create_blueprint()` returning a fully
    configured Blueprint instance.
  - Idempotent `register_blueprint(app)` helper to safely attach
    the blueprint only once.
  - Minimal hard dependencies (only Flask + stdlib here).
  - Provide a stable import surface for init_app in the plugin root.

Expected Companion Route Modules (to be created separately):
  - routes_user.py        (user CRUD on own filters)
  - routes_admin.py       (admin management of any user filters)
  - routes_metrics.py     (metrics endpoint; optional by config)
  - routes_webhook.py     (purchase webhook endpoint)

Each route module should export a single `register(bp: Blueprint)` function
that attaches its endpoints to the passed Blueprint.

Example (routes_user.py):
    def register(bp: Blueprint):
        @bp.route("/filters", methods=["GET"])
        def list_filters():
            ...

Usage in plugin init:
    from .api import register_blueprint
    register_blueprint(app)

The blueprint is mounted at: /plugin/users_books
"""

from __future__ import annotations

from typing import Iterable, Callable
from importlib import import_module
from flask import Blueprint, jsonify
from ..logging_setup import get_logger

LOG = get_logger()

# Blueprint name & URL prefix constants
BLUEPRINT_NAME = "users_books"
URL_PREFIX = "/plugin/users_books"

# Route module specifications: (import_path, attribute_name)
# Each module must provide a function: register(bp: Blueprint) -> None
ROUTE_MODULES: Iterable[str] = (
    "plugins.users_books.api.routes_admin",
    "plugins.users_books.api.routes_ui",  # HTML admin UI
)

def _import_and_register_modules(bp: Blueprint) -> None:
    """
    Dynamically import each route module and invoke its register() function.

    Missing modules are ignored gracefully, allowing optional functionality.
    """
    for mod_path in ROUTE_MODULES:
        try:
            mod = import_module(mod_path)
        except Exception:
            # Silently skip if module not present (optional feature set)
            continue
        register_fn: Callable | None = getattr(mod, "register", None)  # type: ignore
        if callable(register_fn):
            try:
                register_fn(bp)  # type: ignore
            except Exception as exc:  # pragma: no cover - defensive
                LOG.error("Failed registering routes from %s: %s", mod_path, exc)


def create_blueprint() -> Blueprint:
    """
    Create and return the users_books Blueprint with core routes + dynamic modules.

    Includes:
      - /health (basic readiness check)
      - JSON error helper (used optionally by route modules)
    """
    bp = Blueprint(
        BLUEPRINT_NAME,
        __name__,
        url_prefix=URL_PREFIX,
        template_folder="templates"  # enable Jinja templates for UI page(s)
    )

    @bp.route("/health", methods=["GET"])
    def health():
        from .. import config
        return jsonify({
            "plugin": config.PLUGIN_NAME,
            "version": config.PLUGIN_VERSION,
            "status": "ok",
            "config": {
                "db_path": config.get_db_path(),
                "log_level": config.log_level_name(),
            }
        })

    # Attach route modules
    _import_and_register_modules(bp)
    return bp


def register_blueprint(app) -> Blueprint:
    """
    Idempotently build and register the plugin blueprint on the provided Flask app.

    Returns:
      The Blueprint instance (existing or newly created).
    """
    if BLUEPRINT_NAME in app.blueprints:
        return app.blueprints[BLUEPRINT_NAME]
    bp = create_blueprint()
    app.register_blueprint(bp)
    LOG.info("Registered blueprint '%s' at prefix '%s'", BLUEPRINT_NAME, URL_PREFIX)
    return bp


__all__ = [
    "create_blueprint",
    "register_blueprint",
    "BLUEPRINT_NAME",
    "URL_PREFIX",
]
