#!/usr/bin/env python3
"""
seed_settings.py

Purpose
-------
Idempotently pre-create (or validate) the Calibre-Web settings database (app.db),
its encryption key, and (optionally) the users_books plugin database before the
main application entrypoint launches Flask via create_app().

Why
---
Under a fresh deployment the upstream Calibre-Web initialization assumes the
existence (or at least successful on-demand creation) of a `_Settings` row inside
the settings DB. When running inside a custom Docker entrypoint with early
plugin loading, timing can expose AttributeError issues if the settings record
isn't present yet. Pre-seeding eliminates those race/ordering pitfalls and makes
startup deterministic.

What This Script Does
---------------------
1. Resolves the Calibre-Web repository root and ensures it is on sys.path.
2. Determines the config directory (mirrors logic from cps.constants):
     - If environment variable CALIBRE_DBPATH is set -> use that.
       Otherwise fallback to internal default (BASE_DIR or HOME ~ variant).
3. Ensures the config directory exists and is writable.
4. Creates (if missing) the encryption key (.key) in the config directory.
5. Creates (if missing) the SQLite settings DB (app.db) and inserts a default
   `_Settings` row via the upstream helper `load_configuration`.
6. Ensures a Flask session key row exists (flask_settings).
7. Seeds / validates the users_books plugin DB if the plugin is installed:
     - Resolves plugin DB path (respecting USERS_BOOKS_DB_PATH and CALIBRE_DBPATH).
     - Ensures its parent directory exists and is writable.
     - Initializes engine & creates tables.
8. Emits a concise JSON-like summary to stdout.

Safety / Idempotence
--------------------
Running this script multiple times is safe; it will not duplicate rows or
overwrite existing keys or data.

Execution
---------
Typical usage (from within the container image after code copy, before entrypoint_mainwrap.py):
    python entrypoint/seed_settings.py

Environment Variables (recognized)
----------------------------------
CALIBRE_DBPATH              Override config directory location.
USERS_BOOKS_DB_PATH         Relative or absolute path for plugin DB (if plugin present).
USERS_BOOKS_LOG_LEVEL       Logging verbosity for plugin (informational only here).

Exit Codes
----------
0 - Success
>0 - Fatal error (details printed to stderr).

Limitations
-----------
- Assumes calibre-web submodule is present at ./calibre-web relative to this script.
- Does not run full create_app(); only minimal DB + key seeding.
- Does not attempt Google Drive DB seeding (it is created lazily by upstream when enabled).

"""

from __future__ import annotations

import os
import sys
import json
import traceback
from types import SimpleNamespace
from typing import Optional

# ---------------------------------------------------------------------------
# Path Setup
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
CALIBRE_WEB_DIR = os.path.join(REPO_ROOT, "calibre-web")

def _add_path(p: str) -> None:
    if p not in sys.path:
        sys.path.insert(0, p)

_add_path(CALIBRE_WEB_DIR)   # for 'cps'
_add_path(REPO_ROOT)         # for local packages / plugins


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fail(msg: str, code: int = 2):
    print(f"[SEED] FATAL: {msg}", file=sys.stderr)
    sys.exit(code)

def _ensure_dir(path: str):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as exc:
        _fail(f"Unable to create directory '{path}': {exc}")
    if not os.access(path, os.W_OK):
        _fail(f"Directory not writable: {path}")

def _optional_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Calibre-Web Settings Seeding
# ---------------------------------------------------------------------------

def seed_calibre_settings() -> dict:
    """
    Perform minimal Calibre-Web settings DB & key initialization.
    """
    try:
        import cps  # noqa: F401
        from cps import ub, config_sql, constants  # type: ignore
    except Exception as exc:
        _fail(f"Unable to import Calibre-Web modules: {exc}")

    # Resolve config dir similarly to cps.constants logic (reuse constants).
    config_dir = os.environ.get("CALIBRE_DBPATH", getattr(constants, "CONFIG_DIR", None))
    if not config_dir:
        # Fallback: inside submodule, base dir is parent/..
        config_dir = os.path.join(CALIBRE_WEB_DIR, "cps")
    config_dir = os.path.abspath(config_dir)
    _ensure_dir(config_dir)

    settings_filename = getattr(constants, "DEFAULT_SETTINGS_FILE", "app.db")
    settings_path = os.path.join(config_dir, settings_filename)

    # Initialize app settings DB (ub.init_db sets up SQLAlchemy session at ub.session)
    ub.init_db(settings_path)

    # Encryption key (generates if missing)
    key_dir = os.path.dirname(settings_path)
    key, key_error = config_sql.get_encryption_key(key_dir)
    if key_error:
        print(f"[SEED] WARNING: encryption key file write issue: {key_error}", file=sys.stderr)

    # Ensure configuration row & migrations:
    config_sql.load_configuration(ub.session, key)
    # Flask session key:
    _ = config_sql.get_flask_session_key(ub.session)

    # Fetch the (only) settings row to summarize
    from sqlalchemy import text as _sql_text
    settings_row = ub.session.execute(_sql_text("SELECT 1 FROM settings LIMIT 1")).fetchone()
    seeded = bool(settings_row)

    return {
        "config_dir": config_dir,
        "settings_path": settings_path,
        "settings_row_present": seeded,
        "encryption_key_present": True if key else False,
    }


# ---------------------------------------------------------------------------
# users_books Plugin DB Seeding (Optional)
# ---------------------------------------------------------------------------

def seed_users_books_plugin(config_dir: str) -> dict:
    """
    Initialize the users_books plugin DB if the plugin package is importable.
    Returns summary dict (even if plugin absent).
    """
    plugin_summary = {
        "plugin_present": False,
        "db_path": None,
        "initialized": False,
        "error": None,
    }

    mod = _optional_import("users_books")
    if mod is None:
        return plugin_summary  # plugin not present; nothing to do
    plugin_summary["plugin_present"] = True

    try:
        from users_books import config as ub_cfg  # type: ignore
        from users_books import db as ub_db       # type: ignore
    except Exception as exc:
        plugin_summary["error"] = f"import_error: {exc}"
        return plugin_summary

    # Derive DB path using plugin's resolver (which now respects CALIBRE_DBPATH for relative paths).
    db_path = ub_cfg.get_db_path()
    if not os.path.isabs(db_path):
        # Defensive fallback: place relative path under config_dir
        db_path = os.path.join(config_dir, db_path)

    plugin_summary["db_path"] = db_path

    parent = os.path.dirname(os.path.abspath(db_path))
    _ensure_dir(parent)

    try:
        ub_db.init_engine_once()
        plugin_summary["initialized"] = True
    except Exception as exc:
        plugin_summary["error"] = f"init_engine_failed: {exc}"
        # Show traceback for easier debugging
        traceback.print_exc()

    return plugin_summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    overall = SimpleNamespace()
    overall.calibre = seed_calibre_settings()
    overall.plugin_users_books = seed_users_books_plugin(overall.calibre["config_dir"])

    print("[SEED] Calibre-Web + plugin pre-seed summary:")
    print(json.dumps({
        "calibre": overall.calibre,
        "users_books": overall.plugin_users_books,
    }, indent=2, sort_keys=True))

    if not overall.calibre["settings_row_present"]:
        print("[SEED] WARNING: No settings row detected after seeding. Upstream init may still create it.", file=sys.stderr)

    # Exit non-zero only if a fatal error in plugin (optional) isn't desired?
    if overall.plugin_users_books.get("error"):
        # Non-fatal; we treat plugin error as recoverable at this stage.
        print(f"[SEED] NOTE: users_books plugin encountered an issue: {overall.plugin_users_books['error']}", file=sys.stderr)

    print("[SEED] Done.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as se:
        raise
    except Exception as exc:
        _fail(f"Unhandled exception: {exc}", code=99)
