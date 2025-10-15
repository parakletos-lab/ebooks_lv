"""ebooks.lv consolidated admin UI blueprint.

Provides a landing hub under /admin/ebookslv/ linking to custom Mozello
administration tools (orders management, product sync, etc.).

Routes:
    /admin/ebookslv/          -> landing page with navigation buttons
    /admin/ebookslv/orders/   -> Mozello orders admin UI
    /admin/ebookslv/books/    -> placeholder (future feature)

All routes enforce admin access via ensure_admin.
"""
from __future__ import annotations

try:  # runtime dependency, editor may not resolve
    from flask import Blueprint, render_template
    try:
        from flask_wtf.csrf import generate_csrf  # type: ignore
    except Exception:  # pragma: no cover
        def generate_csrf():  # type: ignore
            return ""
except Exception:  # pragma: no cover
    Blueprint = object  # type: ignore
    def render_template(*a, **k):  # type: ignore
        raise RuntimeError("Flask not available")
    def generate_csrf():  # type: ignore
        return ""

from app.utils import ensure_admin, PermissionError
from app.services import books_sync, mozello_service, orders_service
from flask import jsonify, request  # type: ignore
from typing import List, Dict

bp = Blueprint("ebookslv_admin", __name__, url_prefix="/admin/ebookslv", template_folder="../templates")

# Optional CSRF exemption (reuse pattern from users_books) for pure JSON API routes.
try:  # runtime guard
    from cps import csrf  # type: ignore
except Exception:  # pragma: no cover
    csrf = None  # type: ignore

def _maybe_exempt(func):  # type: ignore
    if csrf:  # type: ignore
        try:
            return csrf.exempt(func)  # type: ignore
        except Exception:  # pragma: no cover
            return func
    return func


def _require_admin():
    try:
        ensure_admin()
    except PermissionError as exc:  # type: ignore
        # Minimal JSON-ish fallback (landing is HTML; framework error handler may wrap)
        return {"error": str(exc)}, 403
    return True


@bp.route("/", methods=["GET"])  # /admin/ebookslv/
def landing():  # pragma: no cover - thin render wrapper
    auth = _require_admin()
    if auth is not True:
        return auth
    return render_template("ebookslv_admin.html")


@bp.route("/orders/", methods=["GET"])
def orders_page():  # pragma: no cover - thin render wrapper
    auth = _require_admin()
    if auth is not True:
        return auth
    return render_template("orders_admin.html", ub_csrf_token=generate_csrf())


@bp.route("/books/", methods=["GET"])  # placeholder page
def books_page():  # pragma: no cover - thin render wrapper
    auth = _require_admin()
    if auth is not True:
        return auth
    return render_template("ebookslv_books_admin.html")


# ------------------- Books API (JSON) --------------------
def _json_error(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


def _require_admin_json():
    auth = _require_admin()
    if auth is not True:
        return auth
    return True


@bp.route("/orders/api/list", methods=["GET"])
def api_orders_list():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    data = orders_service.list_orders()
    return jsonify(data)


@bp.route("/orders/api/create", methods=["POST"])
@_maybe_exempt
def api_orders_create():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    payload = request.get_json(silent=True) or {}
    try:
        result = orders_service.create_order(payload.get("email"), payload.get("mz_handle"))
    except orders_service.OrderValidationError as exc:
        return _json_error(str(exc), 400)
    except orders_service.OrderAlreadyExistsError:
        return _json_error("order_exists", 409)
    return jsonify(result)


@bp.route("/orders/api/<int:order_id>/create_user", methods=["POST"])
@_maybe_exempt
def api_orders_create_user(order_id: int):
    auth = _require_admin_json()
    if auth is not True:
        return auth
    try:
        result = orders_service.create_user_for_order(order_id)
    except orders_service.OrderNotFoundError:
        return _json_error("order_missing", 404)
    except orders_service.CalibreUnavailableError:
        return _json_error("calibre_unavailable", 503)
    except orders_service.UserAlreadyExistsError:
        return _json_error("user_exists", 409)
    return jsonify(result)


@bp.route("/orders/api/<int:order_id>/refresh", methods=["POST"])
@_maybe_exempt
def api_orders_refresh(order_id: int):
    auth = _require_admin_json()
    if auth is not True:
        return auth
    try:
        result = orders_service.refresh_order(order_id)
    except orders_service.OrderNotFoundError:
        return _json_error("order_missing", 404)
    return jsonify(result)


@bp.route("/books/api/data", methods=["GET"])  # list calibre only
def api_books_data():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    rows = books_sync.list_calibre_books()
    return jsonify({"rows": rows, "source": "calibre"})


_PRODUCT_CACHE = {"loaded": False, "products": []}


def _merge_products(calibre_rows, products):
    by_handle = {r.get("mz_handle"): r for r in calibre_rows if r.get("mz_handle")}
    # Attach mozello info
    for p in products:
        h = p.get("handle")
        row = by_handle.get(h)
        if row:
            row["mozello_title"] = p.get("title")
            row["mozello_price"] = p.get("price")
    # Orphans
    orphan_rows = []
    for p in products:
        h = p.get("handle")
        if h and h not in by_handle:
            orphan_rows.append({
                "book_id": None,
                "title": None,
                "mz_price": None,
                "mz_handle": h,
                "mozello_title": p.get("title"),
                "mozello_price": p.get("price"),
                "orphan": True,
            })
    # Order: orphans first then calibre rows
    ordered = orphan_rows + calibre_rows
    return ordered


@bp.route("/books/api/load_products", methods=["POST"])  # merge mozello
@_maybe_exempt
def api_books_load_products():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    calibre_rows = books_sync.list_calibre_books()
    ok, data = mozello_service.list_products_full()
    if not ok:
        return _json_error(data.get("error", "mozello_error"), 502)
    products = data.get("products", [])
    merged = _merge_products(calibre_rows, products)
    _PRODUCT_CACHE["loaded"] = True
    _PRODUCT_CACHE["products"] = products
    return jsonify({"rows": merged, "products": len(products), "orphans": len([r for r in merged if r.get("orphan")])})


@bp.route("/books/api/export_one/<int:book_id>", methods=["POST"])
@_maybe_exempt
def api_books_export_one(book_id: int):
    auth = _require_admin_json()
    if auth is not True:
        return auth
    # find book
    rows = books_sync.list_calibre_books()
    target = next((r for r in rows if r["book_id"] == book_id), None)
    if not target:
        return _json_error("book_not_found", 404)
    handle = target.get("mz_handle") or f"book-{book_id}"
    description = books_sync.get_book_description(book_id)
    ok, resp = mozello_service.upsert_product_basic(handle, target.get("title") or f"Book {book_id}", target.get("mz_price"), description)
    if not ok:
        return _json_error(resp.get("error", "export_failed"), 502)
    # Persist handle if new
    if not target.get("mz_handle"):
        books_sync.set_mz_handle(book_id, handle)
        target["mz_handle"] = handle
    # Refresh Mozello info for this row only (lightweight)
    target["mozello_title"] = (resp.get("product") or {}).get("title") if isinstance(resp.get("product"), dict) else target.get("title")
    target["mozello_price"] = target.get("mz_price")
    # Attempt cover upload (best-effort; ignore failures but surface flag)
    cover_uploaded = False
    ok_cov, b64 = books_sync.get_cover_base64(book_id)
    if ok_cov and b64:
        ok_pic, pic_resp = mozello_service.add_product_picture(handle, b64, filename="cover.jpg")
        cover_uploaded = ok_pic
    return jsonify({"row": target, "status": "exported", "cover_uploaded": cover_uploaded})


@bp.route("/books/api/export_all", methods=["POST"])  # create/update all missing handles
@_maybe_exempt
def api_books_export_all():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    rows = books_sync.list_calibre_books()
    to_export = [r for r in rows if not r.get("mz_handle")]
    total = len(to_export)
    success = 0
    failures: List[Dict[str, str]] = []
    cover_attempts = 0
    cover_success = 0
    for r in to_export:
        handle = f"book-{r['book_id']}"
        description = books_sync.get_book_description(r["book_id"])  # type: ignore
        ok, resp = mozello_service.upsert_product_basic(handle, r.get("title") or f"Book {r['book_id']}", r.get("mz_price"), description)
        if ok:
            books_sync.set_mz_handle(r["book_id"], handle)
            r["mz_handle"] = handle
            r["mozello_title"] = r.get("title")
            r["mozello_price"] = r.get("mz_price")
            # Cover upload (best-effort per book)
            ok_cov, b64 = books_sync.get_cover_base64(r["book_id"])  # type: ignore
            if ok_cov and b64:
                cover_attempts += 1
                ok_pic, _ = mozello_service.add_product_picture(handle, b64, filename="cover.jpg")
                if ok_pic:
                    cover_success += 1
            success += 1
        else:
            failures.append({"book_id": r["book_id"], "error": resp.get("error")})
    summary = {"total": total, "success": success, "failed": len(failures), "failures": failures, "cover_attempts": cover_attempts, "cover_success": cover_success}
    return jsonify({"summary": summary, "rows": rows})


@bp.route("/books/api/delete/<handle>", methods=["DELETE"])  # delete product (or orphan)
@_maybe_exempt
def api_books_delete(handle: str):
    auth = _require_admin_json()
    if auth is not True:
        return auth
    ok, resp = mozello_service.delete_product(handle)
    if not ok:
        return _json_error(resp.get("error", "delete_failed"), 502)
    removed = books_sync.clear_mz_handle(handle)
    return jsonify({"status": resp.get("status", "deleted"), "removed_local": removed})


def register_ebookslv_blueprint(app):
    if not getattr(app, "_ebookslv_admin_bp", None):
        app.register_blueprint(bp)
        setattr(app, "_ebookslv_admin_bp", bp)


__all__ = ["register_ebookslv_blueprint", "bp"]
