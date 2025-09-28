"""users_books plugin

Single authoritative implementation of per-user allow‑list filtering for
Calibre‑Web without core source modification or secondary monkeypatch layers.

Responsibilities:
    * users_books SQLite DB + service API
    * Admin blueprint (/plugin/users_books)
    * Admin-only nav link via Jinja loader wrapper
    * Runtime wrapper of ``CalibreDB.common_filters`` adding allow‑list predicate

Deliberately excluded (removed legacy): core runtime patchers, query-level
session monkeypatches, SQLAlchemy before_compile hook, after_request HTML
mutation, runtime core file editing. Single path only for determinism.
"""

from __future__ import annotations

from typing import Any
from functools import wraps

from . import config, services  # re-export
from .logging_setup import get_logger, refresh_level
from .db import init_engine_once, maybe_migrate_schema
from .api import register_blueprint
from .nav_template import register_nav_template_loader
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
    summary = config.summarize_runtime_config()
    log.info("users_books init: version=%s db=%s", PLUGIN_VERSION, summary["db_path"])


def init_app(app: Any) -> None:
    """Initialize plugin (idempotent).

    Steps (single path): logger -> DB init -> blueprint -> nav loader ->
    wrap CalibreDB.common_filters (if not already wrapped) -> one-time log.
    """
    global _LOG_INITIALIZED
    log = get_logger()
    refresh_level()
    if getattr(app, "_users_books_inited", False):  # type: ignore[attr-defined]
        return

    # DB + blueprint
    init_engine_once()
    maybe_migrate_schema()
    register_blueprint(app)

    # Admin nav link (loader wrapping)
    try:  # pragma: no cover
        register_nav_template_loader(app)
    except Exception as exc:  # pragma: no cover
        log.warning("users_books: nav loader failed: %s", exc)

    # Single enforcement path: runtime wrapper of CalibreDB.common_filters
    try:  # pragma: no cover
        from cps import db as core_db  # type: ignore
        original = getattr(core_db.CalibreDB, "common_filters", None)
        if original and not getattr(original, "_users_books_wrapped", False):

            @wraps(original)
            def wrapped(self, *a, **kw):  # type: ignore
                try:
                    from flask import session
                    from sqlalchemy import and_, literal, true  # type: ignore
                    from cps import db as _cdb  # type: ignore
                    from . import services as _svc, config as _cfg, utils as _u
                    base = original(self, *a, **kw)

                    # Identity & privilege
                    raw_uid = session.get("user_id")
                    try:
                        uid = int(raw_uid) if raw_uid is not None else None
                    except Exception:
                        uid = None
                    try:
                        is_admin = _u.is_admin_user()
                    except Exception:
                        is_admin = bool(session.get("is_admin"))
                    if uid is None or is_admin:
                        return base

                    # Config
                    enforce_empty = getattr(_cfg, "enforce_empty_behaviour", lambda: True)()
                    max_ids = getattr(_cfg, "max_ids_in_clause", lambda: 500)()

                    # Allowed IDs
                    try:
                        allowed = _svc.list_user_book_ids(uid, use_cache=False) or []
                    except Exception:
                        allowed = []
                    Books = _cdb.Books  # type: ignore
                    if not allowed:
                        ub_pred = literal(False) if enforce_empty else true()
                    elif len(allowed) > max_ids:
                        ub_pred = true()  # fail-open on excess size
                    else:
                        ub_pred = Books.id.in_(allowed)
                    return and_(base, ub_pred)
                except Exception as e:  # fail-open, never block catalog
                    try:
                        print(f"[users_books wrapper] fail-open: {e}")
                    except Exception:
                        pass
                    return original(self, *a, **kw)

            wrapped._users_books_wrapped = True  # type: ignore[attr-defined]
            setattr(core_db.CalibreDB, "common_filters", wrapped)
            log.info("users_books: installed common_filters wrapper")
    except Exception as exc:  # pragma: no cover
        log.error("users_books: wrapper install failed: %s", exc)

    if not _LOG_INITIALIZED:
        _log_startup_summary(log)
        _LOG_INITIALIZED = True
    setattr(app, "_users_books_inited", True)


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
