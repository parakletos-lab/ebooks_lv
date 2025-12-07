"""Legacy placeholder for retired users_books admin routes.

The Mozello orders implementation replaces this blueprint. Importing this
module is considered an error to surface any lingering references.
"""
from __future__ import annotations


def register_blueprint(app):  # pragma: no cover - defensive guard
    raise RuntimeError("users_books admin routes have been removed; use orders admin")

__all__ = ["register_blueprint"]

"""Admin routes for users ↔ book allow‑list (migrated from legacy plugin).

Primary JSON API namespace: /admin/users_books/*
UI page is now also served at the collection root: /admin/users_books

__all__ = ["register_blueprint"]
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
    # NOTE: Original implementation only returned user_id/book_id making UI unable
    # to display email/title columns. Enrich with lightweight lookups.
    # For now we perform two helper fetches (non-admin users + all books) and map
    # by id. If performance becomes an issue with very large libraries, replace
    # with targeted subset queries.
    rows: List[Dict[str, Any]] = []
    with plugin_session() as s:
        db_rows = (
            s.query(UserFilter)
            .order_by(UserFilter.user_id.asc(), UserFilter.book_id.asc())
            .all()
        )
    # Build lookup dictionaries
    try:
        user_lookup = {u["user_id"]: u.get("email", "") for u in _fetch_non_admin_users()}
    except Exception:  # pragma: no cover
        user_lookup = {}
    try:
        book_lookup = {b["book_id"]: b.get("title", "") for b in _fetch_all_books(None)}
    except Exception:  # pragma: no cover
        book_lookup = {}
    for r in db_rows:
        rows.append({
            "user_id": r.user_id,
            "book_id": r.book_id,
            "email": user_lookup.get(r.user_id, ""),
            "title": book_lookup.get(r.book_id, ""),
        })
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
      1. Try Calibre-Web ORM (preferred) - locate User model in cps.ub (or fallback attr)
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
    # Fallback: raw SQLite (defensive) - minimal columns
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

    @bp.route("/", methods=["GET"])  # UI moved: redirect to new consolidated path
    def admin_ui_root_index():  # pragma: no cover - thin render wrapper
        auth = _require_admin()
        if auth is not True:
            return auth
        return redirect("/admin/ebookslv/users_books/", code=302)

    @bp.route("/admin", methods=["GET"])  # legacy path now redirect
    def admin_ui_root_legacy():  # pragma: no cover - thin wrapper
        auth = _require_admin()
        if auth is not True:
            return auth
        return redirect("/admin/ebookslv/users_books/", code=302)
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
