#!/usr/bin/env python3
"""Create/update a deterministic Mozello order record for the QA non-admin user.

Why: non-admin catalog access uses Mozello orders (users_books DB) to decide
purchased book ids.

Env:
  QA_USER_EMAIL (default: qa_user@example.test)
  QA_ORDER_MZ_HANDLE (default: qa-seeded-handle)
  QA_ORDER_BOOK_ID (optional: if set, uses this calibre book id)

Output JSON: {status,email,mz_handle,calibre_book_id,created}
Exit codes: 0 ok, 2 import/setup error, 3 db error, 4 no books
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import traceback

if "/app" not in sys.path:
    sys.path.insert(0, "/app")


def _calibre_library_root() -> str:
    return os.environ.get("CALIBRE_LIBRARY_PATH") or "/app/library"


def _pick_first_book_id() -> int | None:
    db_path = os.path.join(_calibre_library_root(), "metadata.db")
    if not os.path.exists(db_path):
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT id FROM books ORDER BY id ASC LIMIT 1").fetchone()
            return int(row[0]) if row else None
    except Exception:
        return None


def main() -> int:
    email = (os.environ.get("QA_USER_EMAIL") or "qa_user@example.test").strip().lower()
    mz_handle = (os.environ.get("QA_ORDER_MZ_HANDLE") or "qa-seeded-handle").strip()

    raw_book_id = os.environ.get("QA_ORDER_BOOK_ID")
    if raw_book_id:
        try:
            calibre_book_id = int(raw_book_id)
        except Exception:
            print(json.dumps({"status": "error", "error": "invalid_QA_ORDER_BOOK_ID"}))
            return 2
    else:
        picked = _pick_first_book_id()
        if picked is None:
            print(json.dumps({"status": "error", "error": "no_books"}))
            return 4
        calibre_book_id = picked

    try:
        # Import app-integrated repository layer (service layer not required here)
        from app.db.engine import init_engine_once  # type: ignore
        from app.db.repositories import users_books_repo  # type: ignore
    except Exception:
        traceback.print_exc()
        print(json.dumps({"status": "error", "error": "import_failed"}))
        return 2

    try:
        init_engine_once()
        existing = users_books_repo.get_order_by_email_handle(email, mz_handle)
        if existing:
            users_books_repo.update_links(existing.id, calibre_book_id=calibre_book_id)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "created": False,
                        "email": email,
                        "mz_handle": mz_handle,
                        "calibre_book_id": calibre_book_id,
                    }
                )
            )
            return 0

        users_books_repo.create_order(
            email=email,
            mz_handle=mz_handle,
            calibre_book_id=calibre_book_id,
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "created": True,
                    "email": email,
                    "mz_handle": mz_handle,
                    "calibre_book_id": calibre_book_id,
                }
            )
        )
        return 0
    except Exception as exc:
        traceback.print_exc()
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
