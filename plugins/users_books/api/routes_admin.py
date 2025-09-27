"""Minimal admin JSON API for users_books (cleanup build).

Retained endpoints (used by HTML admin UI):
    GET    /admin/<user_id>/filters
    POST   /admin/<user_id>/filters
    DELETE /admin/<user_id>/filters/<book_id>
    POST   /admin/<user_id>/filters/bulk
    PUT    /admin/<user_id>/filters/upsert

All discovery / expansion / metrics endpoints removed.
"""

from __future__ import annotations

from typing import List, Dict, Any, Iterable
from flask import request, jsonify
import sqlite3
import os

# Upstream (Calibre-Web) imports for user + settings access
try:  # pragma: no cover - defensive runtime import
    from cps import ub as cw_ub  # type: ignore
    from cps import constants as cw_constants  # type: ignore
    from cps.config_sql import _Settings  # type: ignore
except Exception:  # pragma: no cover
    cw_ub = None  # type: ignore
    cw_constants = None  # type: ignore
    _Settings = None  # type: ignore

from .. import services, utils
from ..utils import PermissionError


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
        if isinstance(val, bool):  # skip True/False
            continue
        try:
            iv = int(val)
        except (TypeError, ValueError):
            continue
        out.append(iv)
    if not out:
        raise ValueError("No valid integers found in book_ids")
    return out


def register(bp):  # type: ignore
    """Attach minimal admin routes to blueprint."""

    # ------------------------------------------------------------------
    # Helper: admin guard wrapper for endpoints added below
    # ------------------------------------------------------------------

    def _admin_guard():  # returns True or (resp,status)
        auth = _require_admin()
        if auth is not True:
            return auth
        return True

    # ------------------------------------------------------------------
    # Helper functions for new discovery endpoints (UI compatibility)
    # ------------------------------------------------------------------

    def _library_db_path() -> str | None:
        if cw_ub is None or _Settings is None:
            return None
        try:
            settings = cw_ub.session.query(_Settings).first()
            if not settings or not settings.config_calibre_dir:
                return None
            path = os.path.join(settings.config_calibre_dir, "metadata.db")
            if os.path.isfile(path):
                return path
        except Exception:
            return None
        return None

    def _query_books(limit: int = 500) -> List[Dict[str, Any]]:
        db_path = _library_db_path()
        if not db_path:
            return []
        try:
            # Read-only connection
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            cur = conn.cursor()
            cur.execute("SELECT id, title FROM books ORDER BY id ASC LIMIT ?", (limit,))
            rows = cur.fetchall()
            conn.close()
            return [ {"id": r[0], "title": r[1]} for r in rows ]
        except Exception:
            return []

    def _fetch_user_map(exclude_admin: bool = True) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {}
        if cw_ub is None:
            return out
        try:
            q = cw_ub.session.query(cw_ub.User)
            if exclude_admin and cw_constants is not None:
                q = q.filter((cw_ub.User.role.op('&')(cw_constants.ROLE_ADMIN)) == 0)  # type: ignore
            for u in q.order_by(cw_ub.User.id.asc()).all():
                out[u.id] = {"id": u.id, "email": getattr(u, 'email', None), "name": getattr(u, 'name', None)}
        except Exception:
            return {}
        return out

    def _fetch_user_map_all() -> Dict[int, Dict[str, Any]]:
        return _fetch_user_map(exclude_admin=False)

    def _fetch_titles_for_ids(book_ids: Iterable[int]) -> Dict[int, str]:
        ids = sorted({int(i) for i in book_ids if isinstance(i, int)})
        if not ids:
            return {}
        db_path = _library_db_path()
        if not db_path:
            return {}
        titles: Dict[int, str] = {}
        try:
            uri = f"file:{db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            cur = conn.cursor()
            # Chunk IN clause to avoid SQLite limits
            CHUNK = 500
            for i in range(0, len(ids), CHUNK):
                chunk = ids[i:i+CHUNK]
                qmarks = ",".join(["?"] * len(chunk))
                cur.execute(f"SELECT id, title FROM books WHERE id IN ({qmarks})", tuple(chunk))
                for bid, title in cur.fetchall():
                    titles[bid] = title
            conn.close()
        except Exception:
            return {}
        return titles

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

    # Discovery / expanded endpoints removed.

    # ------------------------------------------------------------------
    # Reintroduced minimal discovery endpoints for Admin UI compatibility
    # ------------------------------------------------------------------

    @bp.route("/admin/all_users", methods=["GET"])
    def admin_all_users():
        if _admin_guard() is not True:  # type: ignore
            return _admin_guard()  # type: ignore
        users = list(_fetch_user_map(exclude_admin=True).values())
        return jsonify({"users": users, "count": len(users)})

    @bp.route("/admin/all_books", methods=["GET"])
    def admin_all_books():
        if _admin_guard() is not True:  # type: ignore
            return _admin_guard()  # type: ignore
        try:
            limit = int(request.args.get("limit", 500))
        except ValueError:
            limit = 500
        books = _query_books(limit=limit)
        return jsonify({"books": books, "count": len(books)})

    @bp.route("/admin/mappings_full", methods=["GET"])
    def admin_mappings_full():
        if _admin_guard() is not True:  # type: ignore
            return _admin_guard()  # type: ignore
        # Load mappings from plugin DB
        from ..db import plugin_session  # local import to avoid cycles
        from ..models import UserFilter  # type: ignore
        rows: List[Dict[str, Any]] = []
        with plugin_session() as s:
            db_rows = s.query(UserFilter).order_by(UserFilter.user_id.asc(), UserFilter.book_id.asc()).all()
        user_ids = [r.user_id for r in db_rows]
        book_ids = [r.book_id for r in db_rows]
        user_map_all = _fetch_user_map_all()
        title_map = _fetch_titles_for_ids(book_ids)
        for r in db_rows:
            u = user_map_all.get(r.user_id, {})
            rows.append({
                "user_id": r.user_id,
                "user_email": u.get("email"),
                "user_name": u.get("name"),
                "book_id": r.book_id,
                "book_title": title_map.get(r.book_id),
            })
        return jsonify({"mappings": rows, "count": len(rows)})


__all__ = ["register"]
