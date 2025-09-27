"""
Configuration utilities for the users_books plugin.

Centralizes:
  - Environment variable parsing
  - Defaults
  - Boolean coercion
  - Plugin metadata

Keeping all environment access in one place makes the rest of the code
(e.g., services, filter hook, API routes) easier to test by monkeypatching
these accessor functions instead of os.environ directly.

Add new configuration getters here as needed, rather than scattering
raw os.getenv calls across the codebase.
"""

from __future__ import annotations

import os
from functools import lru_cache

# ---------------------------------------------------------------------------
# Plugin Metadata
# ---------------------------------------------------------------------------

PLUGIN_NAME = "users_books"
PLUGIN_VERSION = "0.2.0-min"
PLUGIN_DESCRIPTION = "users_books minimal: per-user allow list admin UI + nav button"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = "users_books.db"
DEFAULT_LOG_LEVEL = "INFO"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TRUE_SET = {"1", "true", "yes", "on"}

def _raw_env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    return val if val is not None else default

def env_bool(name: str, default: bool = False) -> bool:  # retained for future extensibility
    raw = _raw_env(name, str(default).lower())
    if raw is None:
        return default
    return raw.lower() in _TRUE_SET

# ---------------------------------------------------------------------------
# Public configuration accessors
# ---------------------------------------------------------------------------

def get_db_path() -> str:
    """
    SQLite path to the plugin's independent data store.

    Resolution precedence:
      1. USERS_BOOKS_DB_PATH (if absolute -> use as-is; if relative and CALIBRE_DBPATH
         is set -> joined underneath that directory)
      2. DEFAULT_DB_PATH (relative) -> if CALIBRE_DBPATH is set, stored inside that dir
         for persistence alongside Calibre-Web's own config DB.

    This keeps the plugin DB colocated with Calibre-Web's config (option 1)
    to avoid permission issues with unwritable working directories and to
    ensure persistence when only /app/config is volume mounted.
    """
    raw = _raw_env("USERS_BOOKS_DB_PATH", DEFAULT_DB_PATH)  # type: ignore[return-value]
    if raw and not os.path.isabs(raw):
        config_root = os.getenv("CALIBRE_DBPATH")
        if config_root:
            return os.path.join(config_root, raw)
    return raw  # type: ignore[return-value]

def session_email_key() -> str:
    return "email"  # minimal build keeps fixed key

def log_level_name() -> str:
    """
    Logging level name (INFO, DEBUG, WARNING, ...).
    """
    return _raw_env("USERS_BOOKS_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()  # type: ignore[return-value]

# ---------------------------------------------------------------------------
# Cached composite views
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def metadata() -> dict:
    """
    Cached plugin metadata for quick reuse (e.g., health/metrics endpoints).
    """
    return {
        "name": PLUGIN_NAME,
        "version": PLUGIN_VERSION,
        "description": PLUGIN_DESCRIPTION,
    }

def summarize_runtime_config() -> dict:
    """
    Non-sensitive snapshot of effective configuration useful for debugging.
    Excludes secrets (like webhook API key).
    """
    return {
        "db_path": get_db_path(),
        "log_level": log_level_name(),
    }

# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Metadata
    "PLUGIN_NAME",
    "PLUGIN_VERSION",
    "PLUGIN_DESCRIPTION",
    # Accessors
    "get_db_path",
    "session_email_key",
    "log_level_name",
    "metadata",
    "summarize_runtime_config",
    # Helpers
    "env_bool",
]
