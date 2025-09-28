"""Database layer root.

Now sources engine/session management from internal app module (migrated
from legacy plugin). The old plugin continues to import these for backward
compatibility during migration.
"""

from .engine import (
    init_engine_once,
    get_engine,
    get_session_factory,
    get_scoped_session,
    app_session as plugin_session,  # maintain exported name used elsewhere
)

__all__ = [
    "init_engine_once",
    "get_engine",
    "get_session_factory",
    "get_scoped_session",
    "plugin_session",
]

