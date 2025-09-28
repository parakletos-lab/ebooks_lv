#!/usr/bin/env python3
"""Validate a user's allow‑list equals EXPECT_IDS.

Env: EMAIL (default test.user@example.org) EXPECT_IDS csv (default 1)
Exit: 0 match, 1 mismatch, 2 error
"""
from __future__ import annotations

import os, sys, json, traceback

EMAIL = os.environ.get("EMAIL", "test.user@example.org").strip().lower()
EXPECT_IDS = [int(x) for x in os.environ.get("EXPECT_IDS", "1").split(",") if x.strip()]

for p in ("/app", "/app/calibre-web", "/app/plugins"):
    if p not in sys.path:
        sys.path.insert(0, p)


def bootstrap():
    try:
        import cps.main  # type: ignore
        from cps import web_server, app as cw_app  # type: ignore
    except Exception:
        return None
    import sys as _s
    orig_start, orig_exit = web_server.start, _s.exit
    web_server.start = lambda: True  # type: ignore
    _s.exit = lambda *_a, **_k: None  # type: ignore
    try:
        cps.main.main()
    except SystemExit:
        pass
    finally:
        web_server.start, _s.exit = orig_start, orig_exit
    try:
        import users_books  # type: ignore
        users_books.init_app(cw_app)
    except Exception:
        pass
    return cw_app


def main():
    if not bootstrap():
        print(json.dumps({"status": "error", "error": "bootstrap_failed"})); return 2
    try:
        import users_books.services as svc  # type: ignore
        from cps import ub  # type: ignore
    except Exception:
        traceback.print_exc(); print(json.dumps({"status": "error", "error": "init_failed"})); return 2
    user = ub.session.query(ub.User).filter(ub.User.email == EMAIL).first()
    if not user:
        print(json.dumps({"status": "error", "error": "user_not_found"})); return 2
    seen = sorted(svc.list_user_book_ids(user.id)); expected = sorted(EXPECT_IDS)
    match = seen == expected
    print(json.dumps({"status": "ok", "user_id": int(user.id), "expected": expected, "seen": seen, "match": match}))
    return 0 if match else 1


if __name__ == "__main__":
    os._exit(main())
