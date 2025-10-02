#!/usr/bin/env python3
"""Create/update deterministic non-admin QA user.

User: qa_filter / filter123
Output: USER <id> CREATED=<bool> EMAIL=<email>
Exit codes: 0 ok, 2 bootstrap/import failure
"""
from __future__ import annotations

import os, sys, traceback

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


def main() -> int:
    if not bootstrap():
        return 2
    try:
        from cps import ub  # type: ignore
        from werkzeug.security import generate_password_hash  # type: ignore
    except Exception:
        traceback.print_exc(); return 2
    s = ub.session
    user = s.query(ub.User).filter(ub.User.name == "qa_filter").first()
    created = False
    if not user:
        user = ub.User(); user.name = "qa_filter"; user.email = "qa_filter@example.test"; user.role = 0; s.add(user); created = True
    user.password = generate_password_hash("filter123")
    s.commit()
    print(f"USER {user.id} CREATED={created} EMAIL={user.email}")
    return 0


if __name__ == "__main__":
    os._exit(main())
