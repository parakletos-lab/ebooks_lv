#!/usr/bin/env python3
"""Minimal Calibre-Web wrapper.

Purpose:
    1. Run upstream `cps.main.main()` while suppressing its internal server start
         and `sys.exit` so we get a configured Flask app object.
    2. Load declared plugin(s) (default: users_books) so they can install DB
         filtering logic (allow‑list) and blueprints.
    3. Expose the Flask `app` for development (app.run) or external WSGI servers.

Intentionally Removed Legacy Helpers:
    - Seeding, diagnostics, library auto-configuration, monkeypatch modules,
        fallback user_loader, and other side-channel patch files.

Environment Variables:
    CALIBRE_WEB_PLUGINS  Comma list of plugin import names (default: users_books)
    CALIBRE_WEB_HOST     Listen address for dev server (default: 0.0.0.0)
    CALIBRE_WEB_PORT     Port for dev server (default: 8083)
    CALIBRE_WEB_DEBUG    1/true/yes/on -> Flask debug

Production:
    Use gunicorn (or similar) instead of the built-in dev server:
            gunicorn -b 0.0.0.0:8083 entrypoint.entrypoint_mainwrap:app
"""

from __future__ import annotations

import os
import sys
import importlib
import traceback
from types import ModuleType
from typing import List, Optional


# -----------------------------------------------------------------------------
# Path Setup
# -----------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CALIBRE_SUBMODULE = os.path.join(BASE_DIR, "calibre-web")
PLUGINS_DIR = os.path.join(BASE_DIR, "plugins")

for path_candidate in (CALIBRE_SUBMODULE, PLUGINS_DIR, BASE_DIR):
    if path_candidate not in sys.path:
        sys.path.insert(0, path_candidate)


def _parse_plugin_env(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [p.strip() for p in raw.split(',') if p.strip()]


# -----------------------------------------------------------------------------
# Upstream main interception
# -----------------------------------------------------------------------------
def _run_upstream_main():
    """Execute upstream `cps.main.main()` with server & exit suppressed.

    Returns the configured Flask app.
    """
    try:
        import cps.main  # type: ignore
        from cps import web_server, app as cw_app  # type: ignore
    except Exception:
        print("[MAINWRAP] FATAL: Unable to import upstream Calibre-Web modules.")
        traceback.print_exc()
        raise SystemExit(2)

    original_start = web_server.start
    original_sys_exit = sys.exit

    def _noop_start():  # noqa: D401
        print("[MAINWRAP] Suppressing internal web_server.start()")
        return True

    def _capture_exit(code: int = 0):  # noqa: D401
        print(f"[MAINWRAP] Suppressed sys.exit({code})")

    web_server.start = _noop_start  # type: ignore
    sys.exit = _capture_exit  # type: ignore
    try:
        cps.main.main()
    except SystemExit:
        pass
    except Exception:
        print("[MAINWRAP] FATAL during upstream main():")
        traceback.print_exc()
        raise
    finally:
        # Restore
        try:
            web_server.start = original_start  # type: ignore
        except Exception:
            pass
        try:
            sys.exit = original_sys_exit  # type: ignore
        except Exception:
            pass
    print("[MAINWRAP] Upstream main complete.")
    return cw_app


# -----------------------------------------------------------------------------
# Auto-configure Calibre library (optional)
# -----------------------------------------------------------------------------
def _load_plugins(app) -> List[str]:
    requested = _parse_plugin_env(os.getenv("CALIBRE_WEB_PLUGINS", "users_books"))
    if not requested:
        print("[MAINWRAP] No plugins requested.")
        return []
    print(f"[MAINWRAP] Loading plugins: {requested}")
    loaded: List[str] = []
    for name in requested:
        try:
            mod: ModuleType = importlib.import_module(name)
            init_fn = getattr(mod, "init_app", None)
            if callable(init_fn):
                init_fn(app)
                loaded.append(name)
                print(f"[PLUGIN:{name}] initialized")
            else:
                print(f"[PLUGIN:{name}] WARNING: init_app missing; skipped")
        except Exception:
            print(f"[PLUGIN:{name}] ERROR during init:")
            traceback.print_exc()
    return loaded


# -----------------------------------------------------------------------------
# Plugin Loader
# -----------------------------------------------------------------------------
def main():  # pragma: no cover - thin wrapper
    app = _run_upstream_main()
    _load_plugins(app)
    return app
    

if __name__ == "__main__":  # Development server only
    application = main()
    host = os.getenv("CALIBRE_WEB_HOST", "0.0.0.0")
    port = int(os.getenv("CALIBRE_WEB_PORT", "8083"))
    debug_raw = os.getenv("CALIBRE_WEB_DEBUG", "")
    debug = debug_raw.lower() in {"1", "true", "yes", "on"}
    # Rely on upstream template auto-reload when debug
    application.run(host=host, port=port, debug=debug)
