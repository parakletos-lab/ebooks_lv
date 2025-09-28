"""Migrated admin routes from plugin (minimal JSON API).

Eventually replaces `plugins.users_books.api.routes_admin`. For now we keep
the same route structure under /plugin/users_books/admin/* so the UI and
existing JS keep working. Once migration complete we can move to a pure
app namespace if desired.
"""
from __future__ import annotations
from typing import List, Dict, Any
try:  # runtime dependency, editor may not resolve
    from flask import Blueprint, request, jsonify  # type: ignore
except Exception:  # pragma: no cover
    Blueprint = object  # type: ignore
    def request():  # type: ignore
        raise RuntimeError("Flask not available")
    def jsonify(*a, **k):  # type: ignore
        return {"error": "Flask missing"}, 500

from app.services import (
    list_allowed_book_ids,
    add_mapping,
    remove_mapping,
    bulk_add,
    upsert,
)
from app.utils import ensure_admin, PermissionError
from app.db import plugin_session
from app.db.models import UserFilter


bp = Blueprint("users_books_admin", __name__, url_prefix="/plugin/users_books")


def _json_error(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


def _require_admin():
    try:
        ensure_admin()
    except PermissionError as exc:  # type: ignore
        return _json_error(str(exc), 403)
    return True


@bp.route("/admin/<int:user_id>/filters", methods=["GET"])
def admin_list_filters(user_id: int):
    auth = _require_admin()
    if auth is not True:
        return auth
    ids = list_allowed_book_ids(user_id)
    return jsonify({"user_id": user_id, "allowed_book_ids": ids, "count": len(ids)})


@bp.route("/admin/<int:user_id>/filters", methods=["POST"])
def admin_add_filter(user_id: int):
    auth = _require_admin()
    if auth is not True:
        return auth
    data = request.get_json(silent=True) or {}
    book_id = data.get("book_id")
    try:
        book_id = int(book_id)
    except Exception:
        return _json_error("Missing or invalid 'book_id'")
    created = add_mapping(user_id, book_id)
    return jsonify({"status": "added" if created else "exists", "user_id": user_id, "book_id": book_id})


@bp.route("/admin/<int:user_id>/filters/<int:book_id>", methods=["DELETE"])
def admin_delete_filter(user_id: int, book_id: int):
    auth = _require_admin()
    if auth is not True:
        return auth
    removed = remove_mapping(user_id, book_id)
    return jsonify({"status": "deleted" if removed else "not_found", "user_id": user_id, "book_id": book_id})


@bp.route("/admin/<int:user_id>/filters/bulk", methods=["POST"])
def admin_bulk_add_filters(user_id: int):
    auth = _require_admin()
    if auth is not True:
        return auth
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("book_ids") or []
    try:
        ids = [int(x) for x in raw_ids if not isinstance(x, bool)]
        if not ids:
            raise ValueError
    except Exception:
        return _json_error("book_ids must be non-empty list of integers")
    summary = bulk_add(user_id, ids)
    summary["user_id"] = user_id
    return jsonify(summary)


@bp.route("/admin/<int:user_id>/filters/upsert", methods=["PUT"])
def admin_upsert_filters(user_id: int):
    auth = _require_admin()
    if auth is not True:
        return auth
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("book_ids") or []
    try:
        ids = [int(x) for x in raw_ids if not isinstance(x, bool)]
        if not ids:
            raise ValueError
    except Exception:
        return _json_error("book_ids must be non-empty list of integers")
    summary = upsert(user_id, ids)
    summary["user_id"] = user_id
    return jsonify(summary)


@bp.route("/admin/mappings_full", methods=["GET"])
def admin_mappings_full():
    auth = _require_admin()
    if auth is not True:
        return auth
    rows: List[Dict[str, Any]] = []
    with plugin_session() as s:
        db_rows = s.query(UserFilter).order_by(UserFilter.user_id.asc(), UserFilter.book_id.asc()).all()
    for r in db_rows:
        rows.append({"user_id": r.user_id, "book_id": r.book_id})
    return jsonify({"mappings": rows, "count": len(rows)})


def register_blueprint(app):
    if not getattr(app, "_users_books_admin_bp", None):
        app.register_blueprint(bp)
        setattr(app, "_users_books_admin_bp", bp)

__all__ = ["register_blueprint", "bp"]
