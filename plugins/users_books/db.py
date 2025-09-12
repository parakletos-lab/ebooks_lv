"""
db.py

Engine & session management for the users_books plugin.

Responsibilities:
  - Lazily initialize a SQLite engine pointing at the configured DB path.
  - Create the ORM schema (idempotent) using models.Base metadata.
  - Provide a scoped_session factory and a context-managed session helper.
  - Offer lightweight utilities for test isolation / reset.
  - Centralize all direct engine/session handling so other modules depend
    only on the higher-level API (services, filter hooks, API routes).

Rationale:
  - Keeping engine setup separate from models avoids circular imports.
  - Using a scoped_session lets us integrate seamlessly with Flask
    request lifecycles if future teardown hooks are added.
  - Explicit reset utilities improve testability without polluting
    production code paths.

Environment / Config:
  - Database file path sourced from config.get_db_path().
  - All logging goes through logging_setup.get_logger().

Thread Safety:
  - Initialization is guarded by a lock to avoid race conditions
    under concurrent startup or test harness scenarios.

Extensibility:
  - If you migrate to a different RDBMS (e.g., Postgres), adjust
    the create_engine call and add any required connection args.
  - For more advanced migrations, integrate Alembic here or in
    a separate migration module.

NOTE:
  - This module intentionally does NOT import any Calibre-Web core
    modules; only plugin-local modules to remain isolated.
"""

from __future__ import annotations

import os, threading
from contextlib import contextmanager
from typing import Optional, Iterator, Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    sessionmaker,
    scoped_session,
    Session as SASession,
)

from . import config
from .models import Base
from .logging_setup import get_logger

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_engine: Optional[Engine] = None
_SessionFactory: Optional[Callable[[], SASession]] = None
_scoped: Optional[scoped_session] = None
_LOCK = threading.Lock()

LOG = get_logger()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def init_engine_once() -> None:
    """
    Initialize the SQLAlchemy engine + session factory exactly once.

    Safe to call multiple times; subsequent calls are no-ops.
    """
    global _engine, _SessionFactory, _scoped
    if _engine is not None:
        return
    with _LOCK:
        if _engine is not None:
            return

        db_path = config.get_db_path()
        LOG.info("Initializing users_books database engine at %s", db_path)

        # Ensure parent directory exists & is writable (startup safety)
        parent_dir = os.path.dirname(os.path.abspath(db_path)) or "."
        try:
            os.makedirs(parent_dir, exist_ok=True)
        except Exception as exc:
            LOG.error("Failed creating plugin DB directory %s: %s", parent_dir, exc)
            raise
        if not os.access(parent_dir, os.W_OK):
            LOG.error("Plugin DB directory %s not writable; check volume/host permissions", parent_dir)
            raise RuntimeError(f"users_books plugin DB directory not writable: {parent_dir}")

        # future=True uses SQLAlchemy 2.0 style behavior where available.
        _engine = create_engine(f"sqlite:///{db_path}", future=True)

        # expire_on_commit=False keeps attribute values accessible after commit
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, class_=SASession)
        _scoped = scoped_session(_SessionFactory)

        # Create tables (idempotent). For real migrations, integrate Alembic.
        Base.metadata.create_all(_engine)
        LOG.debug("Database schema verified/created.")


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

def get_engine() -> Engine:
    """
    Return the SQLAlchemy Engine, lazily initializing if necessary.
    """
    if _engine is None:
        init_engine_once()
    return _engine  # type: ignore[return-value]


def get_session_factory() -> Callable[[], SASession]:
    """
    Return the session factory, lazily initializing if needed.
    """
    if _SessionFactory is None:
        init_engine_once()
    return _SessionFactory  # type: ignore[return-value]


def get_scoped_session() -> scoped_session:
    """
    Return the scoped_session object, lazily initializing if required.

    This prevents RuntimeError in early code paths (e.g. new admin aggregate
    endpoints) that may access the plugin DB before init_app() has been called.
    """
    if _scoped is None:
        init_engine_once()
    if _scoped is None:  # safety net (should not happen)
        raise RuntimeError("Scoped session could not be initialized.")
    return _scoped  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Session context manager
# ---------------------------------------------------------------------------

@contextmanager
def plugin_session() -> Iterator[SASession]:
    """
    Context manager for a plugin DB session.

    Commits on successful exit, rolls back on exception, and always closes.
    """
    scoped = get_scoped_session()
    sess = scoped()
    try:
        yield sess
        sess.commit()
    except Exception:
        sess.rollback()
        raise
    finally:
        sess.close()


# ---------------------------------------------------------------------------
# Testing / Maintenance Utilities
# ---------------------------------------------------------------------------

def reset_for_tests(drop: bool = False) -> None:
    """
    TESTING ONLY: Reset engine & session state for an isolated test environment.

    Parameters:
      drop: If True, drop all tables before re-creation.

    Usage pattern in tests:
        reset_for_tests(drop=True)
        init_engine_once()
        # Run test logic…

    WARNING: Never call this in production runtime.
    """
    global _engine, _SessionFactory, _scoped
    with _LOCK:
        if _engine is not None and drop:
            try:
                Base.metadata.drop_all(_engine)
            except Exception as exc:  # pragma: no cover - defensive
                LOG.warning("Failed dropping tables during reset: %s", exc)
        _engine = None
        _SessionFactory = None
        _scoped = None


def maybe_migrate_schema() -> None:
    """
    Placeholder for future schema migration logic.

    If you adopt Alembic or need ad-hoc SQL migration steps, do them here.
    Currently a no-op.
    """
    # Intentionally empty; hook for future migrations.
    return


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "init_engine_once",
    "get_engine",
    "get_session_factory",
    "get_scoped_session",
    "plugin_session",
    "reset_for_tests",
    "maybe_migrate_schema",
]
