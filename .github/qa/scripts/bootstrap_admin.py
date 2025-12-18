#!/usr/bin/env python3
"""Ensure admin user exists and set deterministic password.

Env (optional):
  QA_ADMIN_USERNAME (default: admin)
    QA_ADMIN_PASSWORD (default: AdminTest123!)
  QA_ADMIN_EMAIL (default: admin@example.org)

Output JSON: {status,created,updated,username,email,role}
Exit codes: 0 ok, 2 bootstrap/import fail, 3 DB error
"""
from __future__ import annotations

import json
import os
import sys
import traceback


def _get_app_db_path() -> str:
    db_dir = os.environ.get("CALIBRE_DBPATH") or "/app/config"
    return os.path.join(db_dir, "app.db")


def _get_session():
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
    if "/app/calibre-web" not in sys.path:
        sys.path.insert(0, "/app/calibre-web")
    from cps import ub  # type: ignore

    ub.app_DB_path = _get_app_db_path()  # type: ignore[attr-defined]
    return ub.init_db_thread()


def main() -> int:
    session = _get_session()

    username = (os.environ.get("QA_ADMIN_USERNAME") or "admin").strip()
    password = os.environ.get("QA_ADMIN_PASSWORD") or "AdminTest123!"
    email = (os.environ.get("QA_ADMIN_EMAIL") or "admin@example.org").strip()

    try:
        from cps import ub, constants  # type: ignore
        from werkzeug.security import generate_password_hash  # type: ignore
    except Exception:
        traceback.print_exc()
        print(json.dumps({"status": "error", "error": "import_failed"}))
        return 2

    created = False
    updated = False
    try:
        user = session.query(ub.User).filter(ub.User.name == username).first()
        if not user:
            user = ub.User()
            user.name = username
            user.email = email
            user.role = constants.ADMIN_USER_ROLES
            session.add(user)
            created = True
        else:
            updated = True
            if email:
                user.email = email
            # Ensure admin bitmask in case user existed but wasn't admin
            user.role = constants.ADMIN_USER_ROLES

        user.password = generate_password_hash(password)
        session.commit()
        print(
            json.dumps(
                {
                    "status": "ok",
                    "created": created,
                    "updated": updated,
                    "username": username,
                    "email": user.email,
                    "role": int(getattr(user, "role", -1)),
                }
            )
        )
        return 0
    except Exception as exc:
        traceback.print_exc()
        try:
            session.rollback()
        except Exception:
            pass
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 3
    finally:
        try:
            session.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
