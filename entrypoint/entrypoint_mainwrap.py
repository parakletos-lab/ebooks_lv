#!/usr/bin/env python3
"""Minimal Calibre-Web wrapper.

Responsibilities:
    1. Execute upstream `cps.main.main()` while preventing its internal server
         start & `sys.exit`, yielding a configured Flask `app` object.
    2. Apply first‑party application wiring under `app/` (routes, services, DB, overrides).
    3. Expose the Flask `app` for development (``app.run``) or production WSGI servers.
"""

from __future__ import annotations

import os
import sys
import traceback


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
    # Calibre-Web's cps.main.main() uses argparse against sys.argv. When running
    # under gunicorn the process argv contains gunicorn's own flags (-b, --workers, etc.)
    # which causes a spurious usage error. Provide a sanitized argv for the
    # duration of the upstream call to keep logs clean.
    original_argv = sys.argv
    sys.argv = [original_argv[0]]  # minimal placeholder (no extra flags)
    try:
        cps.main.main()
    except SystemExit:
        pass
    except Exception:
        print("[MAINWRAP] FATAL during upstream main():")
        traceback.print_exc()
        raise
    finally:
        # restore argv
        try:
            sys.argv = original_argv
        except Exception:
            pass
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
# Plugin Loader
# -----------------------------------------------------------------------------
_APP_SINGLETON = None  # module-level cache


def main():  # pragma: no cover - thin wrapper
    """Create and return the Flask application (idempotent)."""
    global _APP_SINGLETON
    if _APP_SINGLETON is not None:
        return _APP_SINGLETON
    # Bootstrap seeds (settings + library) before upstream main so dynamic
    # calibre-web class generation sees any newly created custom columns.
    # Idempotent & best-effort; failures are logged but not fatal to allow
    # upstream to continue (it can still self-initialize most pieces).
    try:
        from entrypoint import seed as _seed  # type: ignore
        _seed.main()  # orchestrates all seeding; concise logs
    except Exception as exc:  # pragma: no cover
        print(f"[MAINWRAP] WARNING: seeding orchestrator failed: {exc}")
    app = _run_upstream_main()
    try:
        from app.startup import init_app
        init_app(app)
        print("[MAINWRAP] Integrated app wiring complete (explicit call).")
    except Exception as exc:
        print(f"[MAINWRAP] ERROR wiring integrated app: {exc}")
        traceback.print_exc()
    _APP_SINGLETON = app
    return app


# Expose WSGI application object for gunicorn: "gunicorn entrypoint.entrypoint_mainwrap:application"
application = main()


if __name__ == "__main__":  # Development server only (Flask built-in)
    host = os.getenv("CALIBRE_WEB_HOST", "0.0.0.0")
    # Prefer explicit CALIBRE_WEB_PORT, else fall back to generic hosting provider PORT
    port_raw = os.getenv("CALIBRE_WEB_PORT") or os.getenv("PORT") or "8083"
    try:
        port = int(port_raw)
    except ValueError:
        print(f"[MAINWRAP] Invalid port value '{port_raw}', falling back to 8083")
        port = 8083
    debug_raw = os.getenv("CALIBRE_WEB_DEBUG", "")
    debug = debug_raw.lower() in {"1", "true", "yes", "on"}
    application.run(host=host, port=port, debug=debug)
