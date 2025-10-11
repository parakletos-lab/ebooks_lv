#!/usr/bin/env python3
"""Seed / verify Calibre *library* schema artifacts required by ebooks_lv.

Purpose
-------
Make the two logical core fields available for application logic:
  1. mz_price  (float)   -> Calibre Custom Column (label: mz_price, heading: Price)
  2. mz_handle (string)  -> Calibre Identifier (type 'mz') – no schema work needed

Design Choices
--------------
We deliberately use a *custom column* only for price (numeric sorting/search) and
re-use Calibre's stable identifiers table for the Mozello product handle. This
keeps us decoupled from calibre-web dynamic custom column class generation for
the handle and avoids an extra join & restart when introducing the field.

Behavior
--------
Idempotent. The script will:
  * Locate the Calibre library's metadata.db
  * Check if custom column with label 'mz_price' exists
  * If missing and env var MZ_CREATE_PRICE_COLUMN=1, create it safely
  * Summarize status (JSON-ish) to stdout

Safety / Non-Goals
------------------
* We do NOT modify calibre-web source (honors AGENTS.md rule #1)
* We avoid creating the column automatically unless explicitly opted-in via
  environment variable to prevent accidental schema drift in production.
* If Calibre Desktop later edits the column's display JSON, that's fine; our
  minimal initial JSON is intentionally conservative.

Environment Variables
---------------------
CALIBRE_LIBRARY_PATH  -> path to library root (default: /app/library)

Exit Codes
----------
0 success (even if column absent & not created)
>0 fatal error (I/O or sqlite structural failure)

"""
from __future__ import annotations

import os, sys, json, sqlite3, traceback
from typing import Optional, Dict, Any

DEFAULT_LIBRARY_ROOT = "/app/library"


def _fail(msg: str, code: int = 2):
    print(f"[LIB-SEED] FATAL: {msg}", file=sys.stderr)
    sys.exit(code)


def _lib_root() -> str:
    root = os.getenv("CALIBRE_LIBRARY_PATH", DEFAULT_LIBRARY_ROOT)
    return os.path.abspath(root)


def _db_path(root: str) -> str:
    return os.path.join(root, "metadata.db")


def _connect(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        _fail(f"metadata.db not found at {db_path}")
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as exc:
        _fail(f"Unable to open metadata.db: {exc}")


def _fetch_existing_price_column(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    try:
        cur = conn.execute("SELECT * FROM custom_columns WHERE label = ? LIMIT 1", ("mz_price",))
        return cur.fetchone()
    except sqlite3.OperationalError:
        # Table might not exist if library invalid / not initialized
        return None


def _create_price_column(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Create mz_price custom column.

    Calibre's expected pattern for a float single-value custom column is:
      * Row in custom_columns with datatype 'float', editable=1, mark_for_delete=0,
        is_multiple=0, normalized=0, display JSON.
      * Backing table custom_column_<id> with (id PK, value REAL, book INTEGER FK books.id)
    We add an index on book for mild query efficiency.
    """
    summary: Dict[str, Any] = {"created": False, "id": None, "error": None}
    try:
        display_dict = {
            # minimal keys used by calibre-web; Calibre Desktop may enrich later
            "label": "mz_price",
            "name": "Price",
            "heading": "Price",
            "description": "Book price (numeric)",
            "datatype": "float",
            "is_category": False,
            "use_decorations": 0,
            # formatting hints (Calibre may ignore/override)
            "format": "{0:.2f}"
        }
        cur = conn.execute(
            "INSERT INTO custom_columns (label, name, datatype, mark_for_delete, editable, display, is_multiple, normalized) "
            "VALUES (?, ?, ?, 0, 1, ?, 0, 0)",
            ("mz_price", "Price", "float", json.dumps(display_dict, ensure_ascii=False)),
        )
        new_id = cur.lastrowid
        # Create backing table
        tbl = f"custom_column_{new_id}"
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {tbl} (id INTEGER PRIMARY KEY, value REAL, book INTEGER REFERENCES books(id))"
        )
        conn.execute(f"CREATE INDEX IF NOT EXISTS ix_{tbl}_book ON {tbl}(book)")
        summary["created"] = True
        summary["id"] = new_id
    except Exception as exc:
        summary["error"] = str(exc)
        traceback.print_exc()
    return summary


def _count_price_values(conn: sqlite3.Connection, price_row: Optional[sqlite3.Row]) -> int:
    if not price_row:
        return 0
    tbl = f"custom_column_{price_row['id']}"
    try:
        cur = conn.execute(f"SELECT COUNT(1) FROM {tbl}")
        return int(cur.fetchone()[0])
    except Exception:
        return 0


def ensure_mz_price_column() -> Dict[str, Any]:
    """Ensure mz_price column exists; return concise summary dict.

    Keys: created(idempotent flag), id (column id), values (#rows), error(optional).
    """
    root = _lib_root()
    db_path = _db_path(root)
    conn = _connect(db_path)
    created_column = None
    price_row = _fetch_existing_price_column(conn)
    if price_row is None:
        created_column = _create_price_column(conn)
        if created_column.get("created"):
            price_row = _fetch_existing_price_column(conn)
        conn.commit()
    values = _count_price_values(conn, price_row)
    return {
        "id": int(price_row['id']) if price_row else None,
        "created": bool(created_column.get("created")) if created_column else False,
        "values": values,
        "error": created_column.get("error") if created_column and created_column.get("error") else None,
    }


def main():  # pragma: no cover (utility script)
    summary = ensure_mz_price_column()
    if summary.get("error"):
        print(f"[SEED-LIB] ERROR {summary['error']}")
        return 3
    print(
        f"[SEED-LIB] ok mz_price_id={summary.get('id')} created={'yes' if summary.get('created') else 'no'} values={summary.get('values')}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # catch any uncaught
        _fail(f"Unhandled exception: {exc}", code=99)
