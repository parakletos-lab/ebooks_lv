"""Application configuration accessors (plugin-independent).

Centralizes environment variable parsing & defaults. We preserve existing
environment variable names from the legacy plugin for backward compatibility
so operators do not need to change deployment configs immediately.
"""
from __future__ import annotations

import os
from functools import lru_cache

# Metadata (mirrors old plugin, could expand later)
APP_NAME = "users_books"
APP_VERSION = "0.3.0-app"
APP_DESCRIPTION = "Integrated users_books allow-list admin UI"

DEFAULT_DB_PATH = "users_books.db"
DEFAULT_LOG_LEVEL = "INFO"
_TRUE = {"1", "true", "yes", "on"}


def _raw_env(name: str, default: str | None = None) -> str | None:
    val = os.getenv(name)
    return val if val is not None else default


def env_bool(name: str, default: bool = False) -> bool:
    raw = _raw_env(name, str(default).lower())
    if raw is None:
        return default
    return raw.lower() in _TRUE


def get_db_path() -> str:
    raw = _raw_env("USERS_BOOKS_DB_PATH", DEFAULT_DB_PATH)  # legacy var name
    if raw and not os.path.isabs(raw):
        config_root = os.getenv("CALIBRE_DBPATH")
        if config_root:
            return os.path.join(config_root, raw)
    return raw  # type: ignore[return-value]


def session_email_key() -> str:
    # Preserve legacy env variable naming for compatibility
    return os.getenv("USERS_BOOKS_SESSION_EMAIL_KEY", "email")


def log_level_name() -> str:
    return _raw_env("USERS_BOOKS_LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()  # type: ignore[return-value]


@lru_cache(maxsize=1)
def metadata() -> dict:
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
    }


def summarize_runtime_config() -> dict:
    return {
        "db_path": get_db_path(),
        "log_level": log_level_name(),
    }


def app_title() -> str | None:
    """Optional override for Calibre-Web UI title."""
    value = os.getenv("APP_TITLE")
    if value is None:
        return None
    value = value.strip()
    return value or None


__all__ = [
    "APP_NAME",
    "APP_VERSION",
    "APP_DESCRIPTION",
    "get_db_path",
    "session_email_key",
    "log_level_name",
    "metadata",
    "summarize_runtime_config",
    "app_title",
    "env_bool",
]


def public_domain() -> str | None:
    """Public hostname configured for droplet HTTPS (EBOOKSLV_DOMAIN)."""
    value = os.getenv("EBOOKSLV_DOMAIN")
    if value is None:
        return None
    value = value.strip()
    return value or None


__all__.append("public_domain")


def mozello_api_key() -> str | None:
    """Return MOZELLO_API_KEY from environment (no default)."""
    value = os.getenv("MOZELLO_API_KEY")
    if value is None:
        return None
    value = value.strip()
    return value or None

__all__.append("mozello_api_key")


def mozello_store_url() -> str | None:
    """Optional Mozello store URL from environment."""
    value = os.getenv("MOZELLO_STORE_URL")
    if value is None:
        return None
    value = value.strip()
    return value or None

__all__.append("mozello_store_url")


def mozello_webhook_force_port() -> str | None:
    """Optional explicit port to force into computed Mozello webhook URL.

    Environment Variable: MOZELLO_WEBHOOK_FORCE_PORT
    If set (even to default ports 80/443), the port will always be included
    in the advertised notifications_url. This is useful if the upstream
    service stores a literal URL string and you want consistency or are
    behind a proxy that strips Host port details.
    """
    val = os.getenv("MOZELLO_WEBHOOK_FORCE_PORT")
    if not val:
        return None
    return val.strip()

__all__.append("mozello_webhook_force_port")


def mozello_api_base() -> str:
    """Base URL for Mozello API (override with MOZELLO_API_BASE).

    Spec indicates versioned base: https://api.mozello.com/v1/
    We store without trailing slash normalization handled by callers.
    """
    return os.getenv("MOZELLO_API_BASE", "https://api.mozello.com/v1")

__all__.append("mozello_api_base")


def admin_bootstrap_enabled() -> bool:
    """Whether to force-set the Calibre admin password on startup.

    Environment Variable: EBOOKSLV_BOOTSTRAP_ADMIN_PASSWORD

    Default is False to avoid unintended password overrides in production.
    """

    return env_bool("EBOOKSLV_BOOTSTRAP_ADMIN_PASSWORD", default=False)


__all__.append("admin_bootstrap_enabled")


def admin_bootstrap_email() -> str:
    """Admin email to target for bootstrap password changes.

    Environment Variable: EBOOKSLV_ADMIN_EMAIL
    Default: admin@example.org
    """

    return (os.getenv("EBOOKSLV_ADMIN_EMAIL") or "admin@example.org").strip()


__all__.append("admin_bootstrap_email")


def admin_bootstrap_password() -> str:
    """Admin password to apply during bootstrap.

    Environment Variable: EBOOKSLV_ADMIN_PASSWORD
    Default: AdminTest123!
    """

    return os.getenv("EBOOKSLV_ADMIN_PASSWORD", "AdminTest123!")


__all__.append("admin_bootstrap_password")
