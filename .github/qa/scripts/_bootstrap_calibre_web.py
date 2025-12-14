#!/usr/bin/env python3
"""Common Calibre-Web bootstrap for QA scripts.

These scripts are executed inside the calibre-web container.
They import and initialize Calibre-Web without starting the web server.
"""
from __future__ import annotations

import sys


def ensure_sys_path() -> None:
    for p in ("/app", "/app/calibre-web"):
        if p not in sys.path:
            sys.path.insert(0, p)


def bootstrap_calibre_web_app():
    """Return the Calibre-Web Flask app instance or None on failure."""
    ensure_sys_path()
    try:
        import cps.main  # type: ignore
        from cps import web_server, app as cw_app  # type: ignore
    except Exception:
        return None

    orig_start = web_server.start
    orig_exit = sys.exit
    web_server.start = lambda: True  # type: ignore
    sys.exit = lambda *_a, **_k: None  # type: ignore
    try:
        cps.main.main()
    except SystemExit:
        pass
    finally:
        web_server.start = orig_start
        sys.exit = orig_exit

    return cw_app
