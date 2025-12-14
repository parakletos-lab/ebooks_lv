#!/usr/bin/env python3
# Legacy (Archived): admin password reset (plugin-era)
#
# This script referenced the retired users_books plugin/service. Kept for history only.

"""Ensure admin user exists; set password to admin123.

JSON: {status,created,updated,email,role}
Exit codes: 0 ok, 2 bootstrap/import fail, 3 DB error
"""
from __future__ import annotations

import os, sys, json, traceback

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
        from cps import ub, constants  # type: ignore
        from werkzeug.security import generate_password_hash  # type: ignore
    except Exception:
        traceback.print_exc(); print(json.dumps({"status": "error", "error": "import_failed"})); return 2
    s = ub.session
    created = updated = False
    try:
        user = s.query(ub.User).filter(ub.User.name == "admin").first()
        if not user:
            user = ub.User(); user.name = "admin"; user.email = "admin@example.org"; user.role = constants.ADMIN_USER_ROLES; s.add(user); created = True
        else:
            updated = True
        user.password = generate_password_hash("admin123")
        s.commit()
        print(json.dumps({"status": "ok", "created": created, "updated": updated, "email": user.email, "role": int(getattr(user, "role", -1))}))
        return 0
    except Exception as exc:
        traceback.print_exc()
        try: s.rollback()
        except Exception: pass
        print(json.dumps({"status": "error", "error": str(exc)})); return 3


if __name__ == "__main__":
    os._exit(main())
