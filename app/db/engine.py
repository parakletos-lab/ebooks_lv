"""Database engine & session management (migrated from plugin db module).

This file is a near copy of plugins.users_books.db with naming generalized
for the integrated application. The plugin module now delegates here.
"""
from __future__ import annotations

import os, threading
try:  # POSIX file locking for gunicorn multi-worker safety
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - non-POSIX fallback (not expected in droplet)
    fcntl = None  # type: ignore
from contextlib import contextmanager
from typing import Optional, Iterator, Callable

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session as SASession

from app.utils.logging import get_logger
from app.db.models import Base
from app import config as app_config  # re-exports plugin config currently

_engine: Optional[Engine] = None
_SessionFactory: Optional[Callable[[], SASession]] = None
_scoped: Optional[scoped_session] = None
_LOCK = threading.Lock()

LOG = get_logger("users_books.db")


def init_engine_once() -> None:
    global _engine, _SessionFactory, _scoped
    if _engine is not None:
        return
    with _LOCK:
        if _engine is not None:
            return
        db_path = app_config.get_db_path()
        LOG.info("Initializing users_books database engine at %s", db_path)
        parent_dir = os.path.dirname(os.path.abspath(db_path)) or "."
        os.makedirs(parent_dir, exist_ok=True)
        if not os.access(parent_dir, os.W_OK):
            raise RuntimeError(f"users_books DB directory not writable: {parent_dir}")
        _engine = create_engine(f"sqlite:///{db_path}", future=True)
        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, class_=SASession)
        _scoped = scoped_session(_SessionFactory)
        # Cross-process lock to avoid race where multiple gunicorn workers attempt
        # to create the schema simultaneously (window between existence check and
        # DDL emit can trigger 'table ... already exists').
        lock_path = os.path.join(parent_dir, ".users_books_schema.lock")
        if fcntl is not None:
            with open(lock_path, "w") as lf:  # lock file persists (harmless)
                try:
                    fcntl.flock(lf, fcntl.LOCK_EX)
                    _safe_create_schema()
                finally:  # always release
                    try:
                        fcntl.flock(lf, fcntl.LOCK_UN)
                    except Exception:  # pragma: no cover
                        pass
        else:  # Fallback without file lock (best effort)
            _safe_create_schema()
        LOG.debug("users_books schema ready")


def _safe_create_schema():
    """Run metadata.create_all with defensive handling of race errors.

    In high parallel start (multiple gunicorn workers) SQLite may raise
    OperationalError: table X already exists between checkfirst and DDL.
    We swallow those specific messages while surfacing unexpected issues.
    """
    from sqlalchemy.exc import OperationalError  # local import, lightweight
    try:
        if _engine is None:
            return
        # Detect legacy schema (pre-orders) and drop the table for a clean recreate.
        with _engine.begin() as conn:  # type: ignore[assignment]
            table_exists = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='users_books'")
            ).fetchone()
            if table_exists:
                columns = conn.execute(text("PRAGMA table_info('users_books')")).fetchall()
                col_names = {row[1] for row in columns}
                if not {"email", "mz_handle"}.issubset(col_names):
                    LOG.warning("Dropping legacy users_books table prior to Mozello orders schema upgrade")
                    conn.execute(text("DROP TABLE users_books"))
                elif "mz_category_handle" not in col_names:
                    LOG.info("Applying schema migration: adding users_books.mz_category_handle column")
                    conn.execute(text("ALTER TABLE users_books ADD COLUMN mz_category_handle VARCHAR(255)"))
        Base.metadata.create_all(_engine)  # type: ignore[arg-type]
    except OperationalError as e:  # pragma: no cover - concurrency edge
        msg = str(e).lower()
        if "already exists" in msg:
            LOG.warning("Schema create encountered existing tables (benign race)")
        else:
            raise


def get_engine() -> Engine:
    if _engine is None:
        init_engine_once()
    return _engine  # type: ignore[return-value]


def get_session_factory() -> Callable[[], SASession]:
    if _SessionFactory is None:
        init_engine_once()
    return _SessionFactory  # type: ignore[return-value]


def get_scoped_session() -> scoped_session:
    if _scoped is None:
        init_engine_once()
    if _scoped is None:
        raise RuntimeError("Scoped session could not be initialized.")
    return _scoped  # type: ignore[return-value]


@contextmanager
def app_session() -> Iterator[SASession]:
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


# Backward-compatible alias
plugin_session = app_session


def reset_for_tests(drop: bool = False) -> None:
    global _engine, _SessionFactory, _scoped
    with _LOCK:
        if _engine is not None and drop:
            try:
                Base.metadata.drop_all(_engine)
            except Exception:
                LOG.warning("Failed dropping tables during reset", exc_info=True)
        _engine = None
        _SessionFactory = None
        _scoped = None


def maybe_migrate_schema() -> None:  # placeholder
    return


__all__ = [
    "init_engine_once",
    "get_engine",
    "get_session_factory",
    "get_scoped_session",
    "app_session",
    "plugin_session",
    "reset_for_tests",
    "maybe_migrate_schema",
]
