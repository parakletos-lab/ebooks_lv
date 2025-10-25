"""Calibre books ↔ Mozello sync helpers.

Read Calibre metadata.db for book list, mz_price custom column and mz_handle
identifier. Provides minimal read helpers plus identifier insert/delete.
"""
from __future__ import annotations
from typing import Dict, Iterable, List, Optional, Tuple
import os, sqlite3, base64
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


def _identifier_map(conn: sqlite3.Connection, type_name: str) -> Dict[int, str]:
    mapping: Dict[int, str] = {}
    try:
        for row in conn.execute("SELECT book, val FROM identifiers WHERE type=?", (type_name,)):
            value = row[1]
            if isinstance(value, str) and value.strip():
                mapping[int(row[0])] = value.strip()
    except Exception:  # pragma: no cover
        pass
    return mapping


def _get_identifier(conn: sqlite3.Connection, book_id: int, type_name: str) -> Optional[str]:
    try:
        cur = conn.execute(
            "SELECT val FROM identifiers WHERE type=? AND book=? LIMIT 1",
            (type_name, book_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        value = row[0]
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        return None
    except Exception:  # pragma: no cover
        return None


def _set_identifier(book_id: int, type_name: str, value: Optional[str]) -> bool:
    try:
        conn = _connect_rw()
        cleaned = (value or "").strip()
        cur = conn.execute(
            "SELECT val FROM identifiers WHERE book=? AND type=? LIMIT 1",
            (book_id, type_name),
        )
        row = cur.fetchone()
        if not cleaned:
            if row:
                conn.execute("DELETE FROM identifiers WHERE book=? AND type=?", (book_id, type_name))
                conn.commit()
            return True
        if row:
            if row[0] == cleaned:
                return True
            conn.execute("UPDATE identifiers SET val=? WHERE book=? AND type=?", (cleaned, book_id, type_name))
        else:
            conn.execute(
                "INSERT INTO identifiers (book, type, val) VALUES (?, ?, ?)",
                (book_id, type_name, cleaned),
            )
        conn.commit()
        return True
    except Exception as exc:  # pragma: no cover
        LOG.warning("_set_identifier failed type=%s book_id=%s: %s", type_name, book_id, exc)
        return False


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
    handles = _identifier_map(conn, "mz")
    relative_urls = _identifier_map(conn, "mz_relative_url")
    out: List[Dict[str, Optional[str]]] = []
    for r in rows:
        bid = int(r[0])
        out.append({
            "book_id": bid,
            "title": r[1],
            "mz_price": prices.get(bid),
            "mz_handle": handles.get(bid),
            "mz_relative_url": relative_urls.get(bid),
        })
    return out


def _book_path(conn: sqlite3.Connection, book_id: int) -> Optional[str]:
    try:
        cur = conn.execute("SELECT path FROM books WHERE id=? LIMIT 1", (book_id,))
        row = cur.fetchone()
        if not row:
            return None
        return row[0]
    except Exception:  # pragma: no cover
        return None


def get_cover_base64(book_id: int, max_bytes: int = 2_000_000) -> Tuple[bool, Optional[str]]:
    """Return (ok, b64_data) for the book's cover.jpg.

    - Reads library_root/<book.path>/cover.jpg if present.
    - Enforces a soft size cap (default 2MB) to avoid huge uploads.
    - Returns (False, None) if not found or exceeds cap.
    """
    try:
        conn = _connect_rw()
        rel = _book_path(conn, book_id)
        if not rel:
            return False, None
        cover_path = os.path.join(_library_root(), rel, "cover.jpg")
        if not os.path.isfile(cover_path):
            return False, None
        size = os.path.getsize(cover_path)
        if size > max_bytes:
            LOG.warning("cover too large book_id=%s size=%s cap=%s", book_id, size, max_bytes)
            return False, None
        with open(cover_path, "rb") as f:
            raw = f.read()
        b64 = base64.b64encode(raw).decode("ascii")
        return True, b64
    except Exception as exc:  # pragma: no cover
        LOG.warning("get_cover_base64 failed book_id=%s: %s", book_id, exc)
        return False, None


def get_book_description(book_id: int, max_len: int = 8000) -> Optional[str]:
    """Return Calibre book description (HTML) from comments table.

    Calibre stores long description / synopsis in `comments.text` (HTML fragment).
    We return truncated version (max_len chars) to keep Mozello payload modest.
    """
    try:
        conn = _connect_rw()
        cur = conn.execute("SELECT text FROM comments WHERE book=? LIMIT 1", (book_id,))
        row = cur.fetchone()
        if not row:
            return None
        text = row[0] or None
        if not text:
            return None
        if len(text) > max_len:
            return text[:max_len]
        return text
    except Exception as exc:  # pragma: no cover
        LOG.warning("get_book_description failed book_id=%s: %s", book_id, exc)
        return None


def set_mz_handle(book_id: int, handle: str) -> bool:
    """Insert or update mz handle identifier for a book."""
    return _set_identifier(book_id, "mz", handle)


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


def get_mz_handle_for_book(book_id: int) -> Optional[str]:
    """Return Mozello handle for a specific Calibre book if present."""
    conn = _connect_rw()
    return _get_identifier(conn, book_id, "mz")


def set_mz_relative_url(book_id: int, relative_url: Optional[str]) -> bool:
    """Persist Mozello relative storefront URL identifier for a Calibre book."""
    return _set_identifier(book_id, "mz_relative_url", relative_url)


def get_mz_relative_url_for_book(book_id: int) -> Optional[str]:
    conn = _connect_rw()
    return _get_identifier(conn, book_id, "mz_relative_url")


def set_mz_relative_url_for_handle(handle: str, relative_url: Optional[str]) -> bool:
    info = lookup_book_by_handle(handle)
    if not info:
        return False
    book_id = info.get("book_id")
    if book_id is None:
        return False
    try:
        bid = int(book_id)
    except Exception:
        return False
    return set_mz_relative_url(bid, relative_url)


def get_mz_relative_url_for_handle(handle: str) -> Optional[str]:
    info = lookup_book_by_handle(handle)
    if not info:
        return None
    book_id = info.get("book_id")
    if book_id is None:
        return None
    try:
        bid = int(book_id)
    except Exception:
        return None
    return get_mz_relative_url_for_book(bid)


def clear_mz_relative_url_for_handle(handle: str) -> bool:
    return set_mz_relative_url_for_handle(handle, None)


__all__ = [
    "list_calibre_books",
    "set_mz_handle",
    "clear_mz_handle",
    "get_cover_base64",
    "get_book_description",
    "lookup_books_by_handles",
    "lookup_book_by_handle",
    "get_mz_handle_for_book",
    "set_mz_relative_url",
    "get_mz_relative_url_for_book",
    "set_mz_relative_url_for_handle",
    "get_mz_relative_url_for_handle",
    "clear_mz_relative_url_for_handle",
]


def lookup_books_by_handles(handles: Iterable[str]) -> Dict[str, Dict[str, Optional[str]]]:
    """Return mapping of lower-case handle -> book metadata for provided handles."""
    normalized = {h.strip().lower() for h in handles if isinstance(h, str) and h.strip()}
    if not normalized:
        return {}
    conn = _connect_rw()
    placeholders = ",".join(["?"] * len(normalized))
    sql = (
        "SELECT lower(i.val) AS handle, b.id, b.title "
        "FROM identifiers i "
        "JOIN books b ON b.id = i.book "
        "WHERE i.type='mz' AND lower(i.val) IN (" + placeholders + ")"
    )
    rows = conn.execute(sql, tuple(normalized)).fetchall()
    relative_map = _identifier_map(conn, "mz_relative_url")
    result: Dict[str, Dict[str, Optional[str]]] = {}
    for handle, book_id, title in rows:
        key = (handle or "").strip().lower()
        if not key:
            continue
        result[key] = {
            "handle": handle,
            "book_id": int(book_id),
            "title": title,
            "relative_url": relative_map.get(int(book_id)),
        }
    return result


def lookup_book_by_handle(handle: str) -> Optional[Dict[str, Optional[str]]]:
    mapping = lookup_books_by_handles([handle])
    return mapping.get(handle.strip().lower() if isinstance(handle, str) else "")