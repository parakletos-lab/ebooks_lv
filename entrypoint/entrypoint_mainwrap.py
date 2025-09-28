#!/usr/bin/env python3
"""Minimal Calibre-Web wrapper.

Responsibilities:
    1. Execute upstream `cps.main.main()` while preventing its internal server
         start & `sys.exit`, yielding a configured Flask `app` object.
    2. Apply first‑party application wiring under `app/` (routes, services, DB, overrides).
    3. Expose the Flask `app` for development (``app.run``) or production WSGI servers.

Environment Variables (runtime):
    CALIBRE_WEB_HOST   Bind host (default: 0.0.0.0)
    CALIBRE_WEB_PORT   Port (default: 8083)
    CALIBRE_WEB_DEBUG  If set (1/true/yes/on) enables Flask debug (development only)

Production:
    Prefer gunicorn (or similar) over the dev server, e.g.:
            gunicorn -b 0.0.0.0:8083 entrypoint.entrypoint_mainwrap:app
"""

from __future__ import annotations

import os
import sys
import traceback
from typing import Optional


# -----------------------------------------------------------------------------
# Path Setup
# -----------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CALIBRE_SUBMODULE = os.path.join(BASE_DIR, "calibre-web")
APP_DIR = os.path.join(BASE_DIR, "app")

for path_candidate in (CALIBRE_SUBMODULE, APP_DIR, BASE_DIR):
    if path_candidate not in sys.path:
        sys.path.insert(0, path_candidate)


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
def _init_integrated_app(app) -> None:
    """Initialize first-party application layer (idempotent)."""
    try:
        from app.startup import init_app as _init_app  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"[MAINWRAP] Unable to import app.startup.init_app: {exc}")
        return
    try:
        _init_app(app)
        print("[MAINWRAP] Integrated app wiring complete.")
    except Exception:
        print("[MAINWRAP] ERROR during integrated app wiring:")
        traceback.print_exc()


# -----------------------------------------------------------------------------
# Plugin Loader
# -----------------------------------------------------------------------------
def main():  # pragma: no cover - thin wrapper
    app = _run_upstream_main()
    _init_integrated_app(app)
    return app
    

if __name__ == "__main__":  # Development server only
    application = main()
    host = os.getenv("CALIBRE_WEB_HOST", "0.0.0.0")
    port = int(os.getenv("CALIBRE_WEB_PORT", "8083"))
    debug_raw = os.getenv("CALIBRE_WEB_DEBUG", "")
    debug = debug_raw.lower() in {"1", "true", "yes", "on"}
    # Rely on upstream template auto-reload when debug
    application.run(host=host, port=port, debug=debug)
