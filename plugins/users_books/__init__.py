"""
users_books plugin package

Lightweight orchestrator for the split users_books plugin modules.

This file intentionally contains only:
  - Top‑level plugin metadata
  - Public init_app(app) function to integrate with Calibre-Web
  - Minimal re‑exports of commonly used symbols (optional convenience)

All substantive logic now lives in dedicated modules:

  config.py          - Environment / settings accessors & metadata
  logging_setup.py   - Logger creation & helpers
  db.py              - Engine + session management
  models.py          - ORM models (UserFilter)
  cache.py           - Request-scoped caching helpers
  services.py        - Business logic (CRUD, bulk ops, metrics)
  filter_hook.py     - Transparent SQLAlchemy query filtering
  utils.py           - Session/user helpers, dynamic user lookup
  api/
    __init__.py      - Blueprint assembly (/plugin/users_books)
    routes_user.py   - User-facing filter endpoints
    routes_admin.py  - Admin management endpoints
    routes_metrics.py- Metrics & runtime config endpoints
    routes_webhook.py- Purchase webhook (email → user_id → allow-list)

Integration Overview
--------------------
Your outer wrapper (entrypoint) should simply ensure this package is on
PYTHONPATH and then:

    import users_books
    users_books.init_app(app)

The plugin will:
  1. Initialize logging (honors USERS_BOOKS_LOG_LEVEL).
  2. Initialize / migrate (idempotently) the SQLite DB defined by USERS_BOOKS_DB_PATH
     (default: users_books.db).
  3. Register the Flask blueprint at /plugin/users_books (if not already).
  4. Attach the SQLAlchemy filtering hook to SELECT statements.
  5. Log a concise initialization summary.

Environment Variables (See config.py for full list)
---------------------------------------------------
  USERS_BOOKS_DB_PATH
  USERS_BOOKS_MAX_IDS_IN_CLAUSE
  USERS_BOOKS_ENFORCE_EMPTY
  USERS_BOOKS_ENABLE_METRICS
  USERS_BOOKS_WEBHOOK_API_KEY
  USERS_BOOKS_SESSION_EMAIL_KEY
  USERS_BOOKS_LOG_LEVEL

Safe Re-Initialization
----------------------
Calling init_app(app) multiple times is safe; subsequent calls short‑circuit
once components are already attached.

Copyright
---------
SPDX-License-Identifier: MIT (adjust if your project uses a different license)
"""

from __future__ import annotations

from typing import Any

# Internal imports (all local package modules)
from . import config
from .logging_setup import get_logger, refresh_level
from .db import init_engine_once, maybe_migrate_schema
from .filter_hook import attach_filter_hook
from .api import register_blueprint
from .injection import register_response_injection, register_loader_injection
from . import services  # re-export for convenience

# Re-export frequently needed service functions (optional convenience)
from .services import (  # noqa: F401
    list_user_book_ids,
    add_user_book,
    remove_user_book,
    bulk_add_user_books,
    upsert_user_books,
    metrics_snapshot,
)

# Plugin metadata (source of truth: config)
PLUGIN_NAME: str = config.PLUGIN_NAME
PLUGIN_VERSION: str = config.PLUGIN_VERSION
PLUGIN_DESCRIPTION: str = config.PLUGIN_DESCRIPTION

_LOG_INITIALIZED = False


def _log_startup_summary(log):
    """Emit a one-time startup summary (non‑sensitive)."""
    summary = config.summarize_runtime_config()
    log.info(
        "users_books initialized: version=%s db_path=%s metrics=%s enforce_empty=%s "
        "max_ids=%s webhook_enabled=%s",
        PLUGIN_VERSION,
        summary["db_path"],
        summary["metrics_enabled"],
        summary["enforce_empty"],
        summary["max_ids_in_clause"],
        summary["webhook_enabled"],
    )


def init_app(app: Any) -> None:
    """
    Initialize the users_books plugin with the given Flask/Calibre-Web app.

    Steps:
      1. Ensure logger configured & honor current log level.
      2. Initialize database engine & schema.
      3. Register blueprint (idempotent).
      4. Attach filtering hook (idempotent).
      5. Log startup summary once.

    Parameters:
      app: Flask application instance (Calibre-Web's `cps.__init__.app`).
    """
    log = get_logger()
    refresh_level()  # in case env changed since first import
    init_engine_once()
    maybe_migrate_schema()  # currently a no-op placeholder
    register_blueprint(app)
    attach_filter_hook()
    # Register navigation link injection (loader + after_request for robustness)
    try:
        register_loader_injection(app)
        register_response_injection(app)
    except Exception as exc:  # defensive: never break startup due to nav injection
        log.warning("users_books: failed to register nav injection: %s", exc)

    global _LOG_INITIALIZED
    if not _LOG_INITIALIZED:
        _log_startup_summary(log)
        _LOG_INITIALIZED = True


# Public surface of the package
__all__ = [
    # Metadata
    "PLUGIN_NAME",
    "PLUGIN_VERSION",
    "PLUGIN_DESCRIPTION",
    # Init
    "init_app",
    # Config + logger helpers
    "config",
    "get_logger",
    "refresh_level",
    # Services (aggregate re-exports)
    "services",
    "list_user_book_ids",
    "add_user_book",
    "remove_user_book",
    "bulk_add_user_books",
    "upsert_user_books",
    "metrics_snapshot",
]
