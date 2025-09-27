#!/usr/bin/env python3
"""
entrypoint_mainwrap.py

Approach 1: Upstream Main Interception
--------------------------------------
This entrypoint delegates almost all initialization to the original
Calibre-Web bootstrap (cps.main.main) while intercepting the final
web server start & sys.exit so we can inject custom plugins and select
our own serving strategy.

Why this approach:
  - Eliminates fragile manual blueprint registration & login manager wrangling.
  - Preserves upstream ordering (user management decorators, limiter setup, tasks).
  - Minimizes the maintenance burden when upstream adds/changing blueprints.
  - Provides a single, well-defined place for plugin injection.

Sequence:
  1. Adjust sys.path to include submodule + plugins.
  2. (Optional) Run seed_settings.py if RUN_SEED=1 (idempotent).
  3. Monkeypatch cps.web_server.start() to a no-op (returns True).
  4. Monkeypatch sys.exit so upstream main() cannot terminate the container.
  5. Call cps.main.main() (runs create_app(), registers blueprints, etc.).
  6. Restore patched functions.
  7. If provided, auto-configure Calibre library (CALIBRE_LIBRARY_PATH) when metadata.db exists and settings aren't configured yet.
  8. Load declared plugins (CALIBRE_WEB_PLUGINS).
  9. Verify user_loader presence (add fallback if missing).
 10. Start Flask development server (for production override with gunicorn).

Environment Variables:
  CALIBRE_WEB_PLUGINS              Comma list of plugin import names (default: users_books)
  CALIBRE_WEB_HOST                 Listen address (default: 0.0.0.0)
  CALIBRE_WEB_PORT                 Port (default: 8083)
  CALIBRE_WEB_DEBUG                1/true/yes/on to enable Flask debug (also enables template auto-reload)
  CALIBRE_DBPATH                   Path to Calibre-Web settings directory (used by upstream)
  CALIBRE_LIBRARY_PATH             (Optional) Path to a Calibre library (must contain metadata.db)
  RUN_SEED                         If "1", run entrypoint.seed_settings.main() before upstream init
  DEBUG_MAINWRAP                   If set (any value), prints additional diagnostics

Production Deployment:
  Replace the final app.run() with gunicorn, e.g.:
      gunicorn -b 0.0.0.0:8083 entrypoint.entrypoint_mainwrap:app
  (Ensure this file exposes `app` as a module-level symbol.)

Plugin Contract:
  Each plugin must provide an `init_app(app)` function. It can register blueprints,
  attach SQLAlchemy hooks, etc.

Safety:
  - sys.exit and web_server.start are restored after upstream main returns.
  - Exceptions during plugin initialization are caught and logged without aborting.

"""

from __future__ import annotations

import os
import sys
import importlib
import traceback
from types import ModuleType
from typing import List, Callable, Optional


# -----------------------------------------------------------------------------
# Path Setup
# -----------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CALIBRE_SUBMODULE = os.path.join(BASE_DIR, "calibre-web")
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")

for path_candidate in (CALIBRE_SUBMODULE, PLUGINS_DIR, BASE_DIR):
    if path_candidate not in sys.path:
        sys.path.insert(0, path_candidate)


def _debug(msg: str):
    if os.getenv("DEBUG_MAINWRAP"):
        print(f"[MAINWRAP][DEBUG] {msg}")


# -----------------------------------------------------------------------------
# Optional Seeding (idempotent)
# -----------------------------------------------------------------------------
def _maybe_seed():
    if os.getenv("RUN_SEED") == "1":
        try:
            _debug("Running seed_settings.py (RUN_SEED=1)")
            from entrypoint import seed_settings  # type: ignore
            seed_settings.main()
        except Exception:
            print("[MAINWRAP] WARNING: seed_settings failed (continuing):")
            traceback.print_exc()


# -----------------------------------------------------------------------------
# Upstream main interception
# -----------------------------------------------------------------------------
def _run_upstream_main():
    """
    Runs cps.main.main() after monkeypatching web_server.start() and sys.exit.
    Returns (app, user_loader_present_initially).
    """
    try:
        import cps.main  # type: ignore
        from cps import web_server, app, lm  # type: ignore
    except Exception:
        print("[MAINWRAP] FATAL: Unable to import upstream Calibre-Web modules.")
        traceback.print_exc()
        raise SystemExit(2)

    original_start = web_server.start
    original_sys_exit = sys.exit

    exit_code_ref = {"code": 0}

    def _noop_start():
        print("[MAINWRAP] Intercepted web_server.start() (skipping upstream internal server).")
        return True

    def _capture_exit(code: int = 0):
        exit_code_ref["code"] = code
        print(f"[MAINWRAP] Intercepted sys.exit({code}) (suppressed).")

    # Apply monkeypatches
    web_server.start = _noop_start  # type: ignore
    sys.exit = _capture_exit  # type: ignore

    user_loader_present_pre = getattr(lm, "user_callback", None) is not None
    _debug(f"user_loader initial (pre-main): {user_loader_present_pre}")

    try:
        cps.main.main()
    except SystemExit:
        # Upstream might still raise it; we already intercepted sys.exit.
        pass
    except Exception:
        print("[MAINWRAP] FATAL: Exception during upstream main():")
        traceback.print_exc()
        raise
    finally:
        # Restore original functions
        try:
            web_server.start = original_start  # type: ignore
        except Exception:
            pass
        try:
            sys.exit = original_sys_exit  # type: ignore
        except Exception:
            pass

    user_loader_present_post = getattr(lm, "user_callback", None) is not None
    print(f"[MAINWRAP] Upstream main complete. user_loader_present={user_loader_present_post} intercepted_exit_code={exit_code_ref['code']}")
    return app, user_loader_present_post


# -----------------------------------------------------------------------------
# Auto-configure Calibre library (optional)
# -----------------------------------------------------------------------------
def _maybe_configure_library(app):
    lib_dir = os.getenv("CALIBRE_LIBRARY_PATH")
    if not lib_dir:
        return
    if not (os.path.isdir(lib_dir) and os.path.isfile(os.path.join(lib_dir, "metadata.db"))):
        print(f"[MAINWRAP] CALIBRE_LIBRARY_PATH specified but invalid (missing metadata.db): {lib_dir}")
        return
    try:
        from cps import ub, config_sql  # type: ignore
        from cps.config_sql import _Settings  # type: ignore
        # Ensure settings are loaded (they should be already)
        session = ub.session
        settings = session.query(_Settings).first()
        if not settings:
            print("[MAINWRAP] WARNING: No settings row found; cannot set config_calibre_dir.")
            return
        if settings.config_calibre_dir != lib_dir:
            settings.config_calibre_dir = lib_dir
            session.commit()
            print(f"[MAINWRAP] Set config_calibre_dir to {lib_dir}")
        else:
            _debug("Library directory already configured; skipping change.")
    except Exception:
        print("[MAINWRAP] WARNING: Auto library configuration failed:")
        traceback.print_exc()


# -----------------------------------------------------------------------------
# Plugin Loader
# -----------------------------------------------------------------------------
def _parse_plugin_env(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def _load_plugins(app) -> List[str]:
    requested = _parse_plugin_env(os.getenv("CALIBRE_WEB_PLUGINS", "users_books"))
    if not requested:
        print("[MAINWRAP] No plugins requested.")
        return []
    print(f"[MAINWRAP] Loading plugins: {requested}")
    loaded = []
    for name in requested:
        try:
            mod: ModuleType = importlib.import_module(name)
            init_fn: Optional[Callable] = getattr(mod, "init_app", None)
            if callable(init_fn):
                init_fn(app)
                loaded.append(name)
                print(f"[PLUGIN:{name}] Initialized.")
            else:
                print(f"[PLUGIN:{name}] WARNING: init_app() not found; skipped.")
        except Exception:
            print(f"[PLUGIN:{name}] ERROR during initialization:")
            traceback.print_exc()
    print(f"[MAINWRAP] Plugins loaded: {loaded}")
    return loaded


# -----------------------------------------------------------------------------
# Ensure user_loader fallback (last resort)
# -----------------------------------------------------------------------------
def _ensure_user_loader():
    try:
        from cps import lm, ub  # type: ignore
    except Exception:
        print("[MAINWRAP] WARNING: Cannot import login manager for user_loader check.")
        return

    if getattr(lm, "user_callback", None) is not None:
        return

    print("[MAINWRAP] user_loader missing after upstream main; installing fallback.")

    @lm.user_loader  # type: ignore
    def _fallback_user_loader(user_id, random=None, session_key=None):
        try:
            return ub.session.query(ub.User).filter(ub.User.id == int(user_id)).first()
        except Exception:
            return None

    if getattr(lm, "user_callback", None) is not None:
        print("[MAINWRAP] Fallback user_loader installed.")
    else:
        print("[MAINWRAP] WARNING: Failed to install fallback user_loader.")


# -----------------------------------------------------------------------------
# Diagnostics
# -----------------------------------------------------------------------------
def _print_diagnostics(app):
    try:
        from cps import lm  # type: ignore
        user_loader_ok = getattr(lm, "user_callback", None) is not None
    except Exception:
        user_loader_ok = False
    print(f"[MAINWRAP] Diagnostics: user_loader_ok={user_loader_ok} blueprints={list(app.blueprints.keys())}")


# -----------------------------------------------------------------------------
# Main execution
# -----------------------------------------------------------------------------
def main():
    _maybe_seed()
    app, loader_present = _run_upstream_main()
    _maybe_configure_library(app)
    _load_plugins(app)
    if not loader_present:
        _ensure_user_loader()
    _print_diagnostics(app)
    # Template auto-reload now governed solely by CALIBRE_WEB_DEBUG (no separate env var).

    # Development server (production: switch to gunicorn)
    host = os.getenv("CALIBRE_WEB_HOST", "0.0.0.0")
    port_raw = os.getenv("CALIBRE_WEB_PORT", "8083")
    try:
        port = int(port_raw)
    except ValueError:
        print(f"[MAINWRAP] Invalid CALIBRE_WEB_PORT={port_raw!r}, falling back to 8083.")
        port = 8083
    debug_flag = os.getenv("CALIBRE_WEB_DEBUG", "").lower() in ("1", "true", "yes", "on")
    # Explicit reloader control: default OFF to avoid double-initialization side-effects
    use_reloader = os.getenv("CALIBRE_WEB_USE_RELOADER", "").lower() in ("1", "true", "yes", "on") and debug_flag
    if debug_flag:
        try:
            app.jinja_env.auto_reload = True  # type: ignore[attr-defined]
            app.config["TEMPLATES_AUTO_RELOAD"] = True
            print("[MAINWRAP] Template auto-reload enabled (CALIBRE_WEB_DEBUG).")
        except Exception:
            print("[MAINWRAP] WARNING: Failed to enable template auto-reload.")
    print(f"[MAINWRAP] Starting Flask development server on {host}:{port} debug={debug_flag} reloader={use_reloader}")
    # Force threaded server to avoid request blocking; disable reloader unless explicitly enabled
    app.run(host=host, port=port, debug=debug_flag, use_reloader=use_reloader, threaded=True)


# Expose app for WSGI servers (after upstream main we have it).
# If this module is imported by gunicorn AFTER main() call is skipped,
# user may need to call main()/or replicate upstream init. For simplicity,
# we only define 'app' after running upstream sequence when executed directly.
app = None  # Will be replaced in __main__ execution path.

if __name__ == "__main__":
    # Execute full flow and retain the app symbol for external visibility.
    try:
        main()
    except Exception:
        print("[MAINWRAP] Unhandled exception in entrypoint_mainwrap:")
        traceback.print_exc()
        raise
