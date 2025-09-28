"""Admin routes for users ↔ book allow‑list (migrated from legacy plugin).

Primary JSON API namespace: /admin/users_books/*
UI page is now also served at the collection root: /admin/users_books

Backward compatibility:
    /admin/users_books/admin  (legacy dev path) still renders the page
    /users_books/admin        (old public path) now redirects (302) to /admin/users_books
All routes enforce admin access via ``ensure_admin``.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional, Iterable
try:  # runtime dependency, editor may not resolve
    from flask import Blueprint, request, jsonify, redirect  # type: ignore
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
from app.db import models as db_models  # to access User model
import os, sqlite3
from app.utils import constants as app_constants


bp = Blueprint("users_books_admin", __name__, url_prefix="/admin/users_books", template_folder="../templates")

# Optional CSRF exemption (Calibre-Web's global CSRFProtect) for pure JSON API routes.
try:  # runtime guard
    from cps import csrf  # type: ignore
except Exception:  # pragma: no cover
    csrf = None  # type: ignore

# Helper decorator to safely exempt routes from CSRF (works even if csrf is None)
def _maybe_exempt(func):  # type: ignore
    if csrf:  # type: ignore
        try:
            return csrf.exempt(func)  # type: ignore
        except Exception:  # pragma: no cover
            return func
    return func


def _json_error(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


def _require_admin():
    try:
        ensure_admin()
    except PermissionError as exc:  # type: ignore
        return _json_error(str(exc), 403)
    return True


@bp.route("/<int:user_id>/filters", methods=["GET"])
def admin_list_filters(user_id: int):
    auth = _require_admin()
    if auth is not True:
        return auth
    ids = list_allowed_book_ids(user_id)
    return jsonify({"user_id": user_id, "allowed_book_ids": ids, "count": len(ids)})


@bp.route("/<int:user_id>/filters", methods=["POST"])
@_maybe_exempt
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


@bp.route("/<int:user_id>/filters/<int:book_id>", methods=["DELETE"])
@_maybe_exempt
def admin_delete_filter(user_id: int, book_id: int):
    auth = _require_admin()
    if auth is not True:
        return auth
    removed = remove_mapping(user_id, book_id)
    return jsonify({"status": "deleted" if removed else "not_found", "user_id": user_id, "book_id": book_id})


@bp.route("/<int:user_id>/filters/bulk", methods=["POST"])
@_maybe_exempt
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


@bp.route("/<int:user_id>/filters/upsert", methods=["PUT"])
@_maybe_exempt
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

@bp.route("/mappings_full", methods=["GET"])
@_maybe_exempt  # read-only but keep consistent for simplified frontend (no token)
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


# ---------------- Additional discovery endpoints (users/books) -------------

def _metadata_db_path() -> Optional[str]:
    # Reuse CALIBRE_LIBRARY_PATH environment (mounted volume) for books metadata.db
    root = os.getenv("CALIBRE_LIBRARY_PATH") or "/app/library"
    candidate = os.path.join(root, "metadata.db")
    return candidate if os.path.exists(candidate) else None


def _fetch_all_books(limit: Optional[int]) -> List[Dict[str, Any]]:
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
    except Exception:  # pragma: no cover
        return []
    return rows


def _fetch_non_admin_users() -> List[Dict[str, Any]]:
    """Return non-admin, non-anonymous real users.

    Strategy order:
      1. Try Calibre-Web ORM (preferred) – locate User model in cps.ub (or fallback attr)
      2. Fallback to direct SQLite query against app.db if ORM symbols unavailable
    """
    try:
        from cps import constants as cw_consts  # type: ignore
        from cps import ub as cw_ub  # type: ignore
        CWUser = getattr(cw_ub, 'User', None)
        Session = getattr(cw_ub, 'session', None)
        if Session and CWUser:  # SQLAlchemy scoped_session
            try:
                rows = Session.query(CWUser.id, CWUser.email, CWUser.name, CWUser.role).all()
                role_admin = getattr(cw_consts, 'ROLE_ADMIN', 1)
                role_anonymous = getattr(cw_consts, 'ROLE_ANONYMOUS', 0)
                out: List[Dict[str, Any]] = []
                for uid, email, name, role in rows:
                    try:
                        if (role & role_admin) or (role & role_anonymous):
                            continue
                    except Exception:  # pragma: no cover
                        pass
                    out.append({
                        'user_id': int(uid),
                        'email': (email or '').strip(),
                        'name': name or '',
                    })
                out.sort(key=lambda r: (r['email'] or '~', r['user_id']))
                return out
            except Exception:  # pragma: no cover
                pass
    except Exception:  # pragma: no cover
        pass
    # Fallback: raw SQLite (defensive) – minimal columns
    try:
        import sqlite3, os
        db_path = os.path.join(os.getenv('CALIBRE_DBPATH', '/app/config'), 'app.db')
        if not os.path.exists(db_path):  # pragma: no cover
            return []
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        rows = cur.execute('SELECT id, email, name, role FROM user').fetchall()
        # Bitmasks (mirror constants defaults if not importable)
        ROLE_ADMIN = 1
        ROLE_ANONYMOUS = 32
        out: List[Dict[str, Any]] = []
        for uid, email, name, role in rows:
            try:
                if (role & ROLE_ADMIN) or (role & ROLE_ANONYMOUS):
                    continue
            except Exception:  # pragma: no cover
                pass
            out.append({
                'user_id': int(uid),
                'email': (email or '').strip(),
                'name': name or '',
            })
        out.sort(key=lambda r: (r['email'] or '~', r['user_id']))
        return out
    except Exception:  # pragma: no cover
        return []


@bp.route("/all_users", methods=["GET"])
def admin_all_users():
    auth = _require_admin()
    if auth is not True:
        return auth
    users = _fetch_non_admin_users()
    return jsonify({"users": users, "count": len(users)})


@bp.route("/all_books", methods=["GET"])
def admin_all_books():
    auth = _require_admin()
    if auth is not True:
        return auth
    limit = request.args.get("limit", type=int)
    rows = _fetch_all_books(limit)
    return jsonify({"books": rows, "count": len(rows)})


@bp.route("/mappings_full/<int:user_id>/<int:book_id>", methods=["DELETE"])
@_maybe_exempt
def admin_delete_mapping_full(user_id: int, book_id: int):
    """Allow deletion through the expanded mappings table."""
    auth = _require_admin()
    if auth is not True:
        return auth
    removed = remove_mapping(user_id, book_id)
    return jsonify({"status": "deleted" if removed else "not_found", "user_id": user_id, "book_id": book_id})


# ----------------------------- UI Page ------------------------------------
try:  # only define if Flask rendering is available
    from flask import render_template, Blueprint as _FlaskBlueprint  # type: ignore
    try:  # explicit token generation to guarantee presence in template (A)
        from flask_wtf.csrf import generate_csrf  # type: ignore
    except Exception:  # pragma: no cover
        def generate_csrf():  # type: ignore
            return ""

    @bp.route("/", methods=["GET"])  # UI at /admin/users_books
    def admin_ui_root_index():  # pragma: no cover - thin render wrapper
        auth = _require_admin()
        if auth is not True:
            return auth
        # Pass explicit CSRF token so template always renders the hidden input (A/B)
        return render_template("users_books_admin.html", ub_csrf_token=generate_csrf())

    @bp.route("/admin", methods=["GET"])  # legacy path /admin/users_books/admin
    def admin_ui_root_legacy():  # pragma: no cover - thin wrapper
        auth = _require_admin()
        if auth is not True:
            return auth
        return render_template("users_books_admin.html", ub_csrf_token=generate_csrf())
    # Redirect blueprint for deprecated public path /users_books/admin -> /admin/users_books
    redirect_bp = _FlaskBlueprint(
        "users_books_admin_redirects",
        __name__,
    )

    @redirect_bp.route("/users_books/admin", methods=["GET"])  # external old URL
    def users_books_admin_redirect():  # pragma: no cover - thin wrapper
        return redirect("/admin/users_books", code=302)
    @redirect_bp.route("/users_books/admin/", methods=["GET"])  # external old URL with trailing slash
    def users_books_admin_redirect_slash():  # pragma: no cover - thin wrapper
        return redirect("/admin/users_books", code=302)
except Exception:  # pragma: no cover
    pass


def register_blueprint(app):
    # Register API/admin blueprint
    if not getattr(app, "_users_books_admin_bp", None):
        app.register_blueprint(bp)
        setattr(app, "_users_books_admin_bp", bp)
        # Apply csrf exemptions after registration so routes exist
        if csrf:  # type: ignore
            try:  # type: ignore[attr-defined]
                # Exempt the whole blueprint (JSON-only endpoints rely on session admin check)
                csrf.exempt(bp)  # type: ignore[arg-type]
                csrf.exempt(admin_add_filter)
                csrf.exempt(admin_delete_filter)
                csrf.exempt(admin_bulk_add_filters)
                csrf.exempt(admin_upsert_filters)
                csrf.exempt(admin_mappings_full)
                csrf.exempt(admin_delete_mapping_full)
            except Exception:
                pass
    # Register redirect blueprint if defined
    if 'redirect_bp' in globals() and not getattr(app, "_users_books_admin_redirect_bp", None):
        app.register_blueprint(redirect_bp)  # type: ignore[name-defined]
        setattr(app, "_users_books_admin_redirect_bp", redirect_bp)  # type: ignore[name-defined]

__all__ = ["register_blueprint", "bp"]
