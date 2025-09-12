"""
routes_admin.py

Administrator-facing REST API routes for the users_books plugin.

All routes are mounted beneath the main plugin blueprint prefix:
    /plugin/users_books

Core per-user mapping endpoints:
    GET    /admin/<int:target_user_id>/filters
    POST   /admin/<int:target_user_id>/filters
    DELETE /admin/<int:target_user_id>/filters/<int:book_id>
    POST   /admin/<int:target_user_id>/filters/bulk
    PUT    /admin/<int:target_user_id>/filters/upsert

Discovery / full data endpoints (no legacy aggregate endpoints retained):
    GET /admin/all_users        -> ALL non-admin users (id, email, name)
    GET /admin/all_books        -> ALL (or limited) books (id, title)
    GET /admin/mappings_full    -> Expanded mapping list (email + title)
    DELETE /admin/mappings_full/<int:user_id>/<int:book_id>

Rationale:
  The UI constructs allow-list entries by selecting from all non-admin
  users and all books, then adds mappings. Legacy endpoints exposing
  only already-mapped users/books were removed to reduce confusion.

Implementation notes:
  - User data via Calibre-Web app DB (ub.session, ub.User).
  - Book data via direct sqlite3 reads of metadata.db (titles only).
  - Expanded mappings join plugin table with user emails & book titles.

Security:
  - All endpoints require admin (utils.ensure_admin()).
  - Graceful fallbacks return empty lists if metadata.db unavailable.

Performance:
  - Optional ?limit= on /admin/all_books & /admin/mappings_full for
    large libraries; add pagination if future scale demands it.
"""

from __future__ import annotations

from typing import List, Dict, Any, Iterable, Optional, Set

import os
import sqlite3

from flask import request, jsonify

from sqlalchemy import select

from .. import services
from .. import utils
from ..utils import PermissionError
from ..db import plugin_session
from ..models import UserFilter

# Calibre-Web internals (best-effort imports)
from cps import ub, config as cw_config, constants  # type: ignore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _require_admin() -> bool | tuple:
    try:
        utils.ensure_admin()
        return True
    except PermissionError as exc:
        return _json_error(str(exc), 403)


def _coerce_int_list(raw) -> List[int]:
    if not isinstance(raw, (list, tuple)):
        raise ValueError("book_ids must be an array of integers")
    out: List[int] = []
    for val in raw:
        if isinstance(val, bool):
            continue
        try:
            iv = int(val)
        except (TypeError, ValueError):
            continue
        out.append(iv)
    if not out:
        raise ValueError("No valid integers found in book_ids")
    return out


def _metadata_db_path() -> Optional[str]:
    base = getattr(cw_config, "config_calibre_dir", None)
    if not base:
        return None
    path = os.path.join(base, "metadata.db")
    if not os.path.isfile(path):
        return None
    return path


def _fetch_book_rows(book_ids: Iterable[int]) -> Dict[int, str]:
    """
    Given a collection of book_ids, return {book_id: title}.
    Missing IDs are silently ignored.
    """
    ids = sorted({int(b) for b in book_ids if isinstance(b, int)})
    if not ids:
        return {}
    db_path = _metadata_db_path()
    if not db_path:
        return {}
    qmarks = ",".join(["?"] * len(ids))
    sql = f"SELECT id, title FROM books WHERE id IN ({qmarks})"
    out: Dict[int, str] = {}
    try:
        with sqlite3.connect(db_path) as conn:
            for row in conn.execute(sql, ids):
                bid, title = row
                out[int(bid)] = title
    except Exception:
        # On failure, return partial / empty without aborting.
        pass
    return out


def _fetch_all_books(limit: Optional[int]) -> List[Dict[str, Any]]:
    """
    Return list of all (or first N) books: [{book_id, title}, ...]
    """
    db_path = _metadata_db_path()
    if not db_path:
        return []
    sql = "SELECT id, title FROM books ORDER BY id ASC"
    if limit and limit > 0:
        sql += f" LIMIT {int(limit)}"
    rows: List[Dict[str, Any]] = []
    try:
        with sqlite3.connect(db_path) as conn:
            for bid, title in conn.execute(sql):
                rows.append({"book_id": int(bid), "title": title})
    except Exception:
        return []
    return rows


def _fetch_non_admin_users() -> List[Dict[str, Any]]:
    """
    Return all non-admin users from Calibre-Web app DB with id, email, name.
    """
    session = getattr(ub, "session", None)
    UserModel = getattr(ub, "User", None)
    if session is None or UserModel is None:
        return []
    try:
        # ROLE_ADMIN bit test: (role & ROLE_ADMIN) == 0
        role_admin = constants.ROLE_ADMIN
        rows = (
            session.query(UserModel.id, UserModel.email, UserModel.name, UserModel.role)
            .all()
        )
        out: List[Dict[str, Any]] = []
        for uid, email, name, role in rows:
            try:
                if role & role_admin:
                    continue
            except Exception:
                # If role not bitmask-compatible, retain conservative skip if role falsy
                if role:
                    continue
            out.append({
                "user_id": int(uid),
                "email": (email or "").strip(),
                "name": name or "",
            })
        # Sort by email then id for deterministic ordering
        out.sort(key=lambda r: (r["email"] or "~", r["user_id"]))
        return out
    except Exception:
        return []


def _map_user_emails(user_ids: Iterable[int]) -> Dict[int, str]:
    """
    Return {user_id: email} for provided IDs (best-effort).
    """
    uid_set = {int(u) for u in user_ids if isinstance(u, int)}
    if not uid_set:
        return {}
    session = getattr(ub, "session", None)
    UserModel = getattr(ub, "User", None)
    if session is None or UserModel is None:
        return {}
    rows = (
        session.query(UserModel.id, UserModel.email)
        .filter(UserModel.id.in_(uid_set))
        .all()
    )
    return {int(uid): (email or "").strip() for uid, email in rows}


# ---------------------------------------------------------------------------
# Route Registration
# ---------------------------------------------------------------------------

def register(bp):
    """
    Attach admin routes to the provided blueprint.
    """

    # ----- Per-user mapping endpoints (existing) -----

    @bp.route("/admin/<int:target_user_id>/filters", methods=["GET"])
    def admin_list_filters(target_user_id: int):
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        ids = services.list_user_book_ids(target_user_id, use_cache=False)
        return jsonify({
            "user_id": target_user_id,
            "allowed_book_ids": ids,
            "count": len(ids),
        })

    @bp.route("/admin/<int:target_user_id>/filters", methods=["POST"])
    def admin_add_filter(target_user_id: int):
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        data = request.get_json(silent=True) or {}
        book_id = data.get("book_id")
        if not isinstance(book_id, int):
            if isinstance(book_id, str):
                try:
                    book_id = int(book_id)
                except ValueError:
                    return _json_error("Missing or invalid 'book_id' (integer required)")
            else:
                return _json_error("Missing or invalid 'book_id' (integer required)")
        created = services.add_user_book(target_user_id, book_id)
        return jsonify({
            "status": "added" if created else "exists",
            "user_id": target_user_id,
            "book_id": book_id,
        })

    @bp.route("/admin/<int:target_user_id>/filters/<int:book_id>", methods=["DELETE"])
    def admin_delete_filter(target_user_id: int, book_id: int):
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        removed = services.remove_user_book(target_user_id, book_id)
        return jsonify({
            "status": "deleted" if removed else "not_found",
            "user_id": target_user_id,
            "book_id": book_id,
        })

    @bp.route("/admin/<int:target_user_id>/filters/bulk", methods=["POST"])
    def admin_bulk_add_filters(target_user_id: int):
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        data = request.get_json(silent=True) or {}
        raw_ids = data.get("book_ids")
        try:
            ids = _coerce_int_list(raw_ids)
        except ValueError as exc:
            return _json_error(str(exc))
        summary = services.bulk_add_user_books(target_user_id, ids)
        summary["user_id"] = target_user_id
        return jsonify(summary)

    @bp.route("/admin/<int:target_user_id>/filters/upsert", methods=["PUT"])
    def admin_upsert_filters(target_user_id: int):
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        data = request.get_json(silent=True) or {}
        raw_ids = data.get("book_ids")
        try:
            ids = _coerce_int_list(raw_ids)
        except ValueError as exc:
            return _json_error(str(exc))
        summary = services.upsert_user_books(target_user_id, ids)
        summary["user_id"] = target_user_id
        return jsonify(summary)

    # (Legacy aggregate endpoints /admin/users and /admin/books removed)





    # ----- New discovery endpoints (all users / all books) -----

    @bp.route("/admin/all_users", methods=["GET"])
    def admin_all_users():
        """
        Return ALL non-admin users.

        Response:
          200 {
            "users": [
              { "user_id": <int>, "email": "<str>", "name": "<str>" }, ...
            ],
            "count": <int>
          }
        """
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        users = _fetch_non_admin_users()
        return jsonify({"users": users, "count": len(users)})

    @bp.route("/admin/all_books", methods=["GET"])
    def admin_all_books():
        """
        Return all (or first ?limit=) books with id + title.
        Query Params:
          limit (optional int)
        """
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        limit = request.args.get("limit", type=int)
        rows = _fetch_all_books(limit)
        return jsonify({"books": rows, "count": len(rows)})

    # ----- Expanded mappings (email -> book title) -----

    @bp.route("/admin/mappings_full", methods=["GET"])
    def admin_mappings_full():
        """
        Return expanded mapping list with user email + book title.

        Query Params:
          user_id=<int> (optional filter)
          limit=<int>   (optional cap; applied after filtering)

        Response:
          200 {
            "mappings": [
              {
                "user_id": <int>,
                "email": "<str>",
                "book_id": <int>,
                "title": "<str>"
              }, ...
            ],
            "count": <int>
          }
        """
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        user_id_filter = request.args.get("user_id", type=int)
        limit = request.args.get("limit", type=int)

        with plugin_session() as s:
            stmt = select(UserFilter.user_id, UserFilter.book_id).order_by(
                UserFilter.user_id.asc(), UserFilter.book_id.asc()
            )
            if user_id_filter:
                stmt = stmt.where(UserFilter.user_id == user_id_filter)
            rows = s.execute(stmt).all()

        if limit and limit > 0:
            rows = rows[:limit]

        user_ids: Set[int] = {int(r.user_id) for r in rows}
        book_ids: Set[int] = {int(r.book_id) for r in rows}

        email_map = _map_user_emails(user_ids)
        title_map = _fetch_book_rows(book_ids)

        mappings: List[Dict[str, Any]] = []
        for r in rows:
            uid = int(r.user_id)
            bid = int(r.book_id)
            mappings.append({
                "user_id": uid,
                "email": email_map.get(uid, ""),
                "book_id": bid,
                "title": title_map.get(bid, ""),
            })

        return jsonify({"mappings": mappings, "count": len(mappings)})

    @bp.route("/admin/mappings_full/<int:user_id>/<int:book_id>", methods=["DELETE"])
    def admin_mappings_full_delete(user_id: int, book_id: int):
        """
        Convenience delete using expanded mapping list (email->book).
        """
        auth = _require_admin()
        if auth is not True:
            return auth  # type: ignore
        removed = services.remove_user_book(user_id, book_id)
        return jsonify({
            "status": "deleted" if removed else "not_found",
            "user_id": user_id,
            "book_id": book_id,
        })


__all__ = ["register"]
