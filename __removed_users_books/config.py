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
PLUGIN_VERSION = "0.2.0"
PLUGIN_DESCRIPTION = (
    "Per-user allow-list filtering for Calibre-Web with webhook-based purchase integration."
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = "users_books.db"
DEFAULT_MAX_IDS = 500
DEFAULT_ENFORCE_EMPTY = True
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_SESSION_EMAIL_KEY = "email"

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TRUE_SET = {"1", "true", "yes", "on"}

def _raw_env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    return val if val is not None else default

def env_bool(name: str, default: bool = False) -> bool:
    raw = _raw_env(name, str(default).lower())
    if raw is None:
        return default
    return raw.lower() in _TRUE_SET

def env_int(name: str, default: int) -> int:
    raw = _raw_env(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default

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

def max_ids_in_clause() -> int:
    """
    Maximum number of book IDs permitted in an IN(...) filter before fallback.
    Prevents pathological parameter explosion.
    """
    return env_int("USERS_BOOKS_MAX_IDS_IN_CLAUSE", DEFAULT_MAX_IDS)

def enforce_empty_behaviour() -> bool:
    """
    If True, an empty allow-list yields zero results;
    if False, filtering is skipped (lenient).
    """
    return env_bool("USERS_BOOKS_ENFORCE_EMPTY", DEFAULT_ENFORCE_EMPTY)

def metrics_enabled() -> bool:
    """
    Enables /plugin/users_books/metrics endpoint when True.
    """
    return env_bool("USERS_BOOKS_ENABLE_METRICS", False)

def webhook_api_key() -> str | None:
    """
    Returns API key required for purchase webhook.
    If None/empty, webhook is considered disabled.
    """
    key = _raw_env("USERS_BOOKS_WEBHOOK_API_KEY")
    return key.strip() if key else None

def session_email_key() -> str:
    """
    Session dict key under which the user's email is stored (for future UI logic).
    """
    return _raw_env("USERS_BOOKS_SESSION_EMAIL_KEY", DEFAULT_SESSION_EMAIL_KEY)  # type: ignore[return-value]

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
        "max_ids_in_clause": max_ids_in_clause(),
        "enforce_empty": enforce_empty_behaviour(),
        "metrics_enabled": metrics_enabled(),
        "session_email_key": session_email_key(),
        "log_level": log_level_name(),
        "webhook_enabled": webhook_api_key() is not None,
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
    "max_ids_in_clause",
    "enforce_empty_behaviour",
    "metrics_enabled",
    "webhook_api_key",
    "session_email_key",
    "log_level_name",
    "metadata",
    "summarize_runtime_config",
    # Helpers
    "env_bool",
    "env_int",
]
