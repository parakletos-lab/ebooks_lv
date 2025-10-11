"""Calibre books ↔ Mozello sync helpers.

Read Calibre metadata.db for book list, mz_price custom column and mz_handle
identifier. Provides minimal read helpers plus identifier insert/delete.
"""
from __future__ import annotations
from typing import List, Dict, Optional, Tuple
import os, sqlite3
from app.utils.logging import get_logger

LOG = get_logger("books_sync")

DEFAULT_LIBRARY_ROOT = "/app/library"


def _library_root() -> str:
    return os.getenv("CALIBRE_LIBRARY_PATH", DEFAULT_LIBRARY_ROOT)


def _db_path() -> str:
    return os.path.join(_library_root(), "metadata.db")


def _connect_rw() -> sqlite3.Connection:
    path = _db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _mz_price_column_id(conn: sqlite3.Connection) -> Optional[int]:
    try:
        cur = conn.execute("SELECT id FROM custom_columns WHERE label = ? LIMIT 1", ("mz_price",))
        row = cur.fetchone()
        return int(row[0]) if row else None
    except Exception:
        return None


def list_calibre_books(limit: Optional[int] = None) -> List[Dict[str, Optional[str]]]:
    conn = _connect_rw()
    price_id = _mz_price_column_id(conn)
    price_tbl = f"custom_column_{price_id}" if price_id is not None else None
    sql = "SELECT b.id, b.title FROM books b ORDER BY b.id ASC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    prices: Dict[int, float] = {}
    if price_tbl:
        try:
            for r in conn.execute(f"SELECT book, value FROM {price_tbl}"):
                if r[1] is not None:
                    prices[int(r[0])] = float(r[1])
        except Exception:  # pragma: no cover
            pass
    # identifiers (type='mz')
    handles: Dict[int, str] = {}
    try:
        for r in conn.execute("SELECT book, val FROM identifiers WHERE type='mz'"):
            if r[1]:
                handles[int(r[0])] = r[1]
    except Exception:  # pragma: no cover
        pass
    out: List[Dict[str, Optional[str]]] = []
    for r in rows:
        bid = int(r[0])
        out.append({
            "book_id": bid,
            "title": r[1],
            "mz_price": prices.get(bid),
            "mz_handle": handles.get(bid),
        })
    return out


def set_mz_handle(book_id: int, handle: str) -> bool:
    """Insert or update mz handle identifier for a book."""
    try:
        conn = _connect_rw()
        cur = conn.execute("SELECT val FROM identifiers WHERE book=? AND type='mz' LIMIT 1", (book_id,))
        row = cur.fetchone()
        if row:
            if row[0] == handle:
                return True
            conn.execute("UPDATE identifiers SET val=? WHERE book=? AND type='mz'", (handle, book_id))
        else:
            conn.execute("INSERT INTO identifiers (book, type, val) VALUES (?, 'mz', ?)", (book_id, handle))
        conn.commit()
        return True
    except Exception as exc:  # pragma: no cover
        LOG.warning("set_mz_handle failed book_id=%s: %s", book_id, exc)
        return False


def clear_mz_handle(handle: str) -> int:
    """Remove identifier rows matching handle, returns #removed."""
    try:
        conn = _connect_rw()
        cur = conn.execute("DELETE FROM identifiers WHERE type='mz' AND val=?", (handle,))
        conn.commit()
        return cur.rowcount or 0
    except Exception as exc:  # pragma: no cover
        LOG.warning("clear_mz_handle failed handle=%s: %s", handle, exc)
        return 0

__all__ = ["list_calibre_books", "set_mz_handle", "clear_mz_handle"]