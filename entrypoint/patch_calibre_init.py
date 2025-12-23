"""DEPRECATED: patch_calibre_init no longer used (minimal wrapper handles init)."""
from __future__ import annotations

__all__: list[str] = []

import sys
import os
import traceback
from typing import Any

_PATCH_DONE = False
_PATCH_APP = None


def _log(msg: str):  # lightweight logger to stdout (container logs)
    print(f"[PATCH_INIT] {msg}")


def get_patched_app() -> Any:
    global _PATCH_DONE, _PATCH_APP
    if _PATCH_DONE and _PATCH_APP is not None:
        return _PATCH_APP

    # Ensure plugin path available for 'users_books' import inside container
    plugin_path = os.environ.get("USERS_BOOKS_PLUGIN_PATH", "/app/plugins")
    if plugin_path and plugin_path not in sys.path:
        sys.path.insert(0, plugin_path)

    try:
        import cps.main  # type: ignore
        from cps import web_server, app as cw_app  # type: ignore
    except Exception:
        _log("FATAL: unable to import cps modules; traceback follows")
        traceback.print_exc()
        raise

    original_start = web_server.start
    original_exit = sys.exit
    exit_code = {"code": 0}

    def _noop_start():
        _log("Intercept web_server.start() (patch phase)")
        return True

    def _capture_exit(code: int = 0):
        exit_code["code"] = code
        _log(f"Intercept sys.exit({code}) (suppressed during patch)")

    web_server.start = _noop_start  # type: ignore
    sys.exit = _capture_exit  # type: ignore
    try:
        cps.main.main()  # runs upstream init fully
    except SystemExit:
        pass
    except Exception:
        _log("Exception during upstream main(); traceback follows")
        traceback.print_exc()
        raise
    finally:
        # restore originals
        try:
            web_server.start = original_start  # type: ignore
        except Exception:
            pass
        try:
            sys.exit = original_exit  # type: ignore
        except Exception:
            pass

    # cw_app now represents the Flask app created by upstream.
    app = cw_app

    # Initialize plugin (filter hook legacy removed; wrapper enforcement happens later).
    try:
        import users_books  # type: ignore
        users_books.init_app(app)
        # (Filtering now handled by runtime wrapper on CalibreDB.common_filters.)
    except Exception:
        _log("WARNING: users_books plugin initialization failed")
        traceback.print_exc()

    _PATCH_DONE = True
    _PATCH_APP = app
    return app


__all__ = ["get_patched_app"]
