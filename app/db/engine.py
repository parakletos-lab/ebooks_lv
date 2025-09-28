"""Database engine & session management (migrated from plugin db module).

This file is a near copy of plugins.users_books.db with naming generalized
for the integrated application. The plugin module now delegates here.
"""
from __future__ import annotations

import os, threading
from contextlib import contextmanager
from typing import Optional, Iterator, Callable

from sqlalchemy import create_engine
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
        Base.metadata.create_all(_engine)
        LOG.debug("users_books schema ready")


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
