#!/usr/bin/env python3
"""Set (replace) a user's allow‑list to exactly one book.

Env: EMAIL (default test.user@example.org) BOOK_ID(optional)
JSON: {status,user_id,book_id,created_user,final_ids:[...]}
Exit codes: 0 ok, 2 bootstrap/import, 3 mapping error, 4 no books
"""
from __future__ import annotations

import os, sys, json, traceback

EMAIL = os.environ.get("EMAIL", "test.user@example.org").strip().lower()
RAW_BOOK_ID = os.environ.get("BOOK_ID")

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
        from cps import ub, calibre_db, db  # type: ignore
        import users_books.services as svc  # type: ignore
    except Exception:
        traceback.print_exc(); print(json.dumps({"status": "error", "error": "import_failed"})); return 2
    if RAW_BOOK_ID:
        try:
            chosen_id = int(RAW_BOOK_ID)
        except Exception:
            print(json.dumps({"status": "error", "error": "invalid_BOOK_ID"})); return 2
    else:
        first = calibre_db.session.query(db.Books).order_by(db.Books.id.asc()).first()
        if not first:
            print(json.dumps({"status": "error", "error": "no_books"})); return 4
        chosen_id = int(first.id)
    s = ub.session
    user = s.query(ub.User).filter(ub.User.email == EMAIL).first(); created = False
    if not user:
        user = ub.User(); user.name = EMAIL.split("@")[0]; user.email = EMAIL; user.password = ""; user.role = 0; s.add(user); s.commit(); created = True
    try:
        svc.replace_user_books(user.id, [chosen_id])
        final_ids = svc.list_user_book_ids(user.id)
        print(json.dumps({"status": "ok", "user_id": int(user.id), "book_id": chosen_id, "created_user": created, "final_ids": final_ids})); return 0
    except Exception as exc:
        traceback.print_exc(); print(json.dumps({"status": "error", "error": str(exc)})); return 3


if __name__ == "__main__":
    os._exit(main())

