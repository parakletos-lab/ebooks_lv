"""users_books plugin (minimal build)

Scope intentionally reduced to only:
  - Independent SQLite DB (users_books table: user_id, book_id)
  - Admin CRUD JSON endpoints (see routes_admin.py)
  - Simple HTML admin UI page (routes_ui.py)
  - Navigation button injection ("ebooks.lv") for admins
  - Basic logging + runtime summary

Removed components: filtering hook, caching layer, metrics, webhook, user self-service,
debug routes. Leftover files have been deleted to keep footprint lean.

Initialization:
    import users_books
    users_books.init_app(app)

Effects:
  1. Configure logger (USERS_BOOKS_LOG_LEVEL optional).
  2. Initialize database (create table if missing).
  3. Register blueprint at /plugin/users_books.
  4. Register nav injection helpers.
  5. Log one-line startup summary.

Idempotent: calling init_app multiple times is safe.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

from typing import Any

# Internal imports (all local package modules)
from . import config
from .logging_setup import get_logger, refresh_level
from .db import init_engine_once, maybe_migrate_schema
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
    "users_books initialized: version=%s db_path=%s",
    PLUGIN_VERSION,
    summary["db_path"],
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
]
