"""ebooks.lv consolidated admin UI blueprint.

Provides a landing hub under /admin/ebookslv/ linking to custom Mozello
administration tools (orders management, product sync, etc.).

Routes:
    /admin/ebookslv/          -> landing page with navigation buttons
    /admin/ebookslv/orders/   -> Mozello orders admin UI
    /admin/ebookslv/books/    -> Books sync with Mozello store

All routes enforce admin access via ensure_admin.
"""
from __future__ import annotations

try:  # runtime dependency, editor may not resolve
    from flask import Blueprint, render_template, redirect, url_for
    try:
        from flask_wtf.csrf import generate_csrf  # type: ignore
    except Exception:  # pragma: no cover
        def generate_csrf():  # type: ignore
            return ""
except Exception:  # pragma: no cover
    Blueprint = object  # type: ignore
    def render_template(*a, **k):  # type: ignore
        raise RuntimeError("Flask not available")
    def redirect(*a, **k):  # type: ignore
        raise RuntimeError("Flask not available")
    def url_for(*a, **k):  # type: ignore
        return "/"
    def generate_csrf():  # type: ignore
        return ""

try:  # runtime dependency on Calibre-Web
    from cps.render_template import render_title_template as _cw_render_title_template  # type: ignore
except Exception:  # pragma: no cover - allow tests without Calibre runtime
    _cw_render_title_template = None  # type: ignore

from app.config import app_title
from app.utils import ensure_admin, PermissionError
from app.utils.logging import get_logger
from app.services.calibre_defaults_service import apply_ebookslv_default_settings, CalibreRuntimeUnavailable
try:  # pragma: no cover - Flask-Babel optional in tests
    from flask_babel import gettext as _  # type: ignore
except Exception:  # pragma: no cover
    def _fallback_gettext(message, **kwargs):
        if kwargs:
            try:
                return message % kwargs
            except Exception:
                return message
        return message

    _ = _fallback_gettext  # type: ignore

from app.services import (
    books_sync,
    mozello_service,
    orders_service,
    fetch_templates_context,
    save_email_template,
    TemplateValidationError,
)
from flask import jsonify, request  # type: ignore
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

bp = Blueprint("ebookslv_admin", __name__, url_prefix="/admin/ebookslv", template_folder="../templates")
LOG = get_logger("ebookslv.admin")

_ERROR_MESSAGES = {
    "calibre_runtime_unavailable": _("Calibre runtime is unavailable. Try again later."),
    "order_exists": _("This Mozello order already exists."),
    "order_missing": _("Order could not be found."),
    "calibre_unavailable": _("Calibre is currently unavailable."),
    "user_exists": _("User already exists."),
    "email_required": _("Email address is required."),
    "mz_handle_required": _("Mozello handle is required."),
    "invalid_date": _("Enter valid dates in YYYY-MM-DD format."),
    "invalid_date_range": _("End date must be on or after the start date."),
    "invalid_payload": _("Server returned an invalid payload."),
    "mozello_error": _("Mozello API request failed."),
    "book_not_found": _("Book not found in the Calibre library."),
    "delete_failed": _("Delete request failed."),
    "export_failed": _("Export failed."),
    "mozello_import_failed": _("Mozello import failed."),
    "api_key_missing": _("Mozello API key is missing."),
    "invalid_json": _("Mozello API returned invalid JSON."),
    "http_error": _("Mozello API request failed."),
    "not_found": _("Product not found in Mozello store."),
    "handle_required": _("Mozello handle is required."),
    "unsupported_language": _("Selected language is not supported."),
    "unsupported_template": _("Template key is not supported."),
    "subject_multiline": _("Subject must be a single line."),
    "subject_too_long": _("Subject is too long."),
}

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


def _login_redirect():
    try:
        login_url = url_for("web.login")
    except Exception:
        login_url = "/login"
    target = request.full_path or request.path or "/"
    if target.endswith("?"):
        target = target[:-1]
    payload = urlencode({"next": target})
    separator = "&" if "?" in login_url else "?"
    destination = f"{login_url}{separator}{payload}"
    return redirect(destination)


def _ensure_admin(prefer_redirect: bool = False):
    try:
        ensure_admin()
    except PermissionError as exc:  # type: ignore
        if prefer_redirect:
            return _login_redirect()
        return {"error": str(exc)}, 403
    return True


def _require_admin():
    return _ensure_admin(prefer_redirect=True)


def _render_admin_page(template_name: str, **context):
    """Render admin pages with the same context Calibre-Web uses (instance + sidebar)."""
    if _cw_render_title_template:  # type: ignore[truthy-bool]
        try:
            return _cw_render_title_template(template_name, **context)  # type: ignore[misc]
        except Exception:
            pass
    return render_template(template_name, **context)


@bp.route("/", methods=["GET"])  # /admin/ebookslv/
def landing():  # pragma: no cover - thin render wrapper
    auth = _require_admin()
    if auth is not True:
        return auth
    return _render_admin_page("ebookslv_admin.html", ub_csrf_token=generate_csrf())


@bp.route("/orders/", methods=["GET"])
def orders_page():  # pragma: no cover - thin render wrapper
    auth = _require_admin()
    if auth is not True:
        return auth
    return _render_admin_page("orders_admin.html", ub_csrf_token=generate_csrf())


@bp.route("/books/", methods=["GET"])
def books_page():  # pragma: no cover - thin render wrapper
    auth = _require_admin()
    if auth is not True:
        return auth
    return _render_admin_page("ebookslv_books_admin.html")


@bp.route("/email-templates/", methods=["GET"])
def email_templates_page():  # pragma: no cover - render wrapper
    auth = _require_admin()
    if auth is not True:
        return auth
    context = fetch_templates_context()
    return _render_admin_page(
        "email_templates_admin.html",
        ub_csrf_token=generate_csrf(),
        templates_context=context,
    )


# ------------------- Books API (JSON) --------------------
def _error_message_for(code: str) -> Optional[str]:
    return _ERROR_MESSAGES.get(code)


def _json_error(
    code: str,
    status: int = 400,
    *,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
):
    payload: Dict[str, Any] = {"error": code}
    final_message = message or _error_message_for(code)
    if final_message:
        payload["message"] = final_message
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status


def _require_admin_json():
    auth = _ensure_admin(prefer_redirect=False)
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


@bp.route("/apply_defaults", methods=["POST"])
@_maybe_exempt
def api_apply_defaults():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    try:
        result = apply_ebookslv_default_settings()
    except CalibreRuntimeUnavailable as exc:
        LOG.warning("Unable to apply default user configuration: %s", exc)
        code = str(exc) or "calibre_runtime_unavailable"
        return _json_error(code, 503)
    LOG.info(
        "Applied ebooks.lv default Calibre settings roles_mask=%s visibility_mask=%s upload_enabled=%s title=%s",
        result.get("roles_mask"),
        result.get("visibility_mask"),
        result.get("upload_enabled"),
        result.get("title"),
    )
    return jsonify({"status": "ok", "result": result})


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


@bp.route("/orders/api/import_paid", methods=["POST"])
@_maybe_exempt
def api_orders_import_paid():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    payload = request.get_json(silent=True) or {}
    try:
        result = orders_service.import_paid_orders(
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
        )
    except orders_service.OrderValidationError as exc:
        return _json_error(str(exc), 400)
    except orders_service.OrderImportError as exc:
        reason = str(exc)
        return _json_error(
            "mozello_import_failed",
            502,
            message=_("Mozello import failed: %(reason)s", reason=reason),
        )
    return jsonify(result)


@bp.route("/orders/api/<int:order_id>", methods=["DELETE"])
@_maybe_exempt
def api_orders_delete(order_id: int):
    auth = _require_admin_json()
    if auth is not True:
        return auth
    try:
        result = orders_service.delete_order(order_id)
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


def _extract_relative_url(
    payload: Any,
    *,
    preferred_language: Optional[str] = None,
    force_refresh: bool = False,
) -> Optional[str]:
    if payload is None:
        return None
    return mozello_service.derive_relative_url_from_product(
        payload,
        preferred_language=preferred_language,
        force_refresh=force_refresh,
    )


def _merge_products(calibre_rows, products):
    by_handle = {r.get("mz_handle"): r for r in calibre_rows if r.get("mz_handle")}
    # Attach mozello info
    for p in products:
        h = p.get("handle")
        row = by_handle.get(h)
        if row:
            row["mozello_title"] = p.get("title")
            row["mozello_price"] = p.get("price")
            relative_value = p.get("relative_url")
            row["mz_relative_url"] = relative_value or row.get("mz_relative_url")
    # Orphans
    orphan_rows = []
    for p in products:
        h = p.get("handle")
        if h and h not in by_handle:
            relative_value = p.get("relative_url")
            orphan_rows.append({
                "book_id": None,
                "title": None,
                "mz_price": None,
                "mz_handle": h,
                "mozello_title": p.get("title"),
                "mozello_price": p.get("price"),
                "mz_relative_url": relative_value,
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
        code = data.get("error") if isinstance(data, dict) else None
        status_hint = None
        if isinstance(data, dict):
            status_hint = data.get("status")
        message = None
        if status_hint:
            message = _("Mozello API request failed (HTTP %(status)s).", status=status_hint)
        return _json_error(code or "mozello_error", 502, message=message, details=data if isinstance(data, dict) else None)
    products = data.get("products", [])
    for p in products:
        handle = (p.get("handle") or "").strip()
        if not handle:
            continue
        relative_value = p.get("relative_url")
        if relative_value:
            books_sync.set_mz_relative_url_for_handle(handle, relative_value)
        else:
            books_sync.clear_mz_relative_url_for_handle(handle)
    merged = _merge_products(calibre_rows, products)
    _PRODUCT_CACHE["loaded"] = True
    _PRODUCT_CACHE["products"] = products
    return jsonify({"rows": merged, "products": len(products), "orphans": len([r for r in merged if r.get("orphan")])})


@bp.route("/books/api/sync_prices_from_mozello", methods=["POST"])
@_maybe_exempt
def api_sync_prices_from_mozello():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    calibre_rows = books_sync.list_calibre_books()
    by_handle = {r.get("mz_handle"): r for r in calibre_rows if r.get("mz_handle")}
    ok, data = mozello_service.list_products_full()
    if not ok:
        return _json_error(data.get("error") if isinstance(data, dict) else "mozello_error", 502, details=data if isinstance(data, dict) else None)
    products = data.get("products", []) if isinstance(data, dict) else []
    updated = 0
    missing_price = 0
    orphans = 0
    for p in products:
        handle = (p.get("handle") or "").strip()
        if not handle:
            continue
        price_value = p.get("price")
        row = by_handle.get(handle)
        if not row:
            orphans += 1
            continue
        current_price = row.get("mz_price")
        if price_value is None:
            missing_price += 1
            continue
        if current_price == price_value:
            continue
        if books_sync.set_mz_price_for_handle(handle, price_value):
            row["mz_price"] = price_value
            updated += 1
    return jsonify({"status": "ok", "updated": updated, "missing_price": missing_price, "orphans": orphans, "rows": calibre_rows})


@bp.route("/books/api/push_prices_to_mozello", methods=["POST"])
@_maybe_exempt
def api_push_prices_to_mozello():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    calibre_rows = books_sync.list_calibre_books()
    handles_with_price = [r for r in calibre_rows if r.get("mz_handle") and r.get("mz_price") is not None]
    ok_products, data = mozello_service.list_products_full()
    remote_price_map = {}
    if ok_products and isinstance(data, dict):
        for p in data.get("products", []) or []:
            h = (p.get("handle") or "").strip()
            if h:
                remote_price_map[h] = p.get("price")
    success = 0
    skipped_same = 0
    failures = []
    for r in handles_with_price:
        handle = r.get("mz_handle")
        price_value = r.get("mz_price")
        if handle in remote_price_map and remote_price_map[handle] == price_value:
            skipped_same += 1
            continue
        ok_update, resp = mozello_service.update_product_price(handle, price_value)
        if ok_update:
            success += 1
        else:
            failures.append({"handle": handle, "error": resp.get("error") if isinstance(resp, dict) else "unknown"})
    summary = {
        "total": len(handles_with_price),
        "success": success,
        "skipped_same": skipped_same,
        "failed": len(failures),
        "failures": failures,
    }
    return jsonify({"status": "ok", "summary": summary})


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
    language_code = target.get("language_code") if isinstance(target, dict) else None
    ok, resp = mozello_service.upsert_product_basic(
        handle,
        target.get("title") or f"Book {book_id}",
        target.get("mz_price"),
        description,
        language_code,
    )
    if not ok:
        LOG.error(
            "Export book failed book_id=%s handle=%s details=%s",
            book_id,
            handle,
            resp,
        )
        msg_code = "export_failed"
        status_hint = None
        if isinstance(resp, dict):
            msg_code = resp.get("error") or msg_code
            status_hint = resp.get("status") or resp.get("update_status") or resp.get("create_status")
        details_payload = resp if isinstance(resp, dict) else {"raw": resp}
        message = None
        if status_hint:
            message = _("Export failed (status %(status)s).", status=status_hint)
        return _json_error(msg_code, 502, message=message, details=details_payload)
    # Persist handle if new
    if not target.get("mz_handle"):
        books_sync.set_mz_handle(book_id, handle)
        target["mz_handle"] = handle
    # Refresh Mozello info for this row only (lightweight)
    target["mozello_title"] = (resp.get("product") or {}).get("title") if isinstance(resp.get("product"), dict) else target.get("title")
    target["mozello_price"] = target.get("mz_price")
    relative_url = target.get("mz_relative_url")
    candidate = _extract_relative_url(resp, preferred_language=language_code, force_refresh=True)
    if candidate:
        relative_url = candidate
    elif not relative_url:
        ok_product, product_payload = mozello_service.fetch_product(handle)
        if ok_product:
            relative_url = _extract_relative_url(
                product_payload,
                preferred_language=language_code,
                force_refresh=True,
            )
    if relative_url:
        target["mz_relative_url"] = relative_url
        books_sync.set_mz_relative_url_for_handle(handle, relative_url)
    else:
        target["mz_relative_url"] = None
        books_sync.clear_mz_relative_url_for_handle(handle)
    # Attempt cover sync (best-effort; preserve tracked cover uids if present)
    cover_uploaded = False
    ok_cov, b64 = books_sync.get_cover_base64(book_id)
    if ok_cov and b64:
        tracked = books_sync.get_mz_cover_picture_uids_for_book(book_id)
        ok_cover, cover_resp = mozello_service.ensure_cover_picture_present(
            handle,
            tracked_picture_uids=tracked,
            cover_b64=b64,
        )
        cover_uploaded = ok_cover and isinstance(cover_resp, dict) and cover_resp.get("status") == "uploaded"
        if ok_cover and isinstance(cover_resp, dict):
            new_uid = cover_resp.get("uploaded_uid")
            if isinstance(new_uid, str) and new_uid.strip():
                books_sync.set_mz_cover_picture_uids(book_id, [new_uid.strip()])
    return jsonify({"row": target, "status": "exported", "cover_uploaded": cover_uploaded})


@bp.route("/books/api/export_all", methods=["POST"])  # create/update all missing handles
@_maybe_exempt
def api_books_export_all():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    rows = books_sync.list_calibre_books()
    def _has_positive_price(value: Any) -> bool:
        if value is None:
            return False
        try:
            return float(value) > 0.0
        except Exception:
            return False

    to_export = [r for r in rows if (not r.get("mz_handle")) and _has_positive_price(r.get("mz_price"))]
    total = len(to_export)
    success = 0
    failures: List[Dict[str, str]] = []
    cover_attempts = 0
    cover_success = 0
    for r in to_export:
        handle = f"book-{r['book_id']}"
        description = books_sync.get_book_description(r["book_id"])  # type: ignore
        language_code = r.get("language_code")
        ok, resp = mozello_service.upsert_product_basic(
            handle,
            r.get("title") or f"Book {r['book_id']}",
            r.get("mz_price"),
            description,
            language_code,
        )
        if ok:
            books_sync.set_mz_handle(r["book_id"], handle)
            r["mz_handle"] = handle
            r["mozello_title"] = r.get("title")
            r["mozello_price"] = r.get("mz_price")
            relative_url = _extract_relative_url(
                resp,
                preferred_language=language_code,
                force_refresh=True,
            )
            if not relative_url:
                ok_product, product_payload = mozello_service.fetch_product(handle)
                if ok_product:
                    relative_url = _extract_relative_url(
                        product_payload,
                        preferred_language=language_code,
                        force_refresh=True,
                    )
            if relative_url:
                r["mz_relative_url"] = relative_url
                books_sync.set_mz_relative_url_for_handle(handle, relative_url)
            else:
                books_sync.clear_mz_relative_url_for_handle(handle)
            # Cover upload (best-effort per book, and track uploaded uid)
            ok_cov, b64 = books_sync.get_cover_base64(r["book_id"])  # type: ignore
            if ok_cov and b64:
                cover_attempts += 1
                tracked = books_sync.get_mz_cover_picture_uids_for_book(r["book_id"])  # type: ignore
                ok_cover, cover_resp = mozello_service.ensure_cover_picture_present(
                    handle,
                    tracked_picture_uids=tracked,
                    cover_b64=b64,
                    filename="cover.jpg",
                )
                if ok_cover and isinstance(cover_resp, dict):
                    new_uid = cover_resp.get("uploaded_uid")
                    if isinstance(new_uid, str) and new_uid.strip():
                        books_sync.set_mz_cover_picture_uids(r["book_id"], [new_uid.strip()])  # type: ignore
                    if cover_resp.get("status") == "uploaded":
                        cover_success += 1
            success += 1
        else:
                failures.append({"book_id": r["book_id"], "error": resp.get("error") if isinstance(resp, dict) else "unknown"})
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
        code = resp.get("error", "delete_failed") if isinstance(resp, dict) else "delete_failed"
        status_hint = resp.get("status") if isinstance(resp, dict) else None
        message = None
        if status_hint:
            message = _("Mozello API request failed (HTTP %(status)s).", status=status_hint)
        return _json_error(code, 502, message=message, details=resp if isinstance(resp, dict) else None)
    removed_handle = books_sync.clear_mz_handle(handle)
    books_sync.clear_mz_relative_url_for_handle(handle)
    books_sync.clear_mz_cover_picture_uids_for_handle(handle)
    return jsonify({"status": resp.get("status", "deleted"), "removed_local": removed_handle})


@bp.route("/email-templates/api/list", methods=["GET"])
def api_email_templates_list():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    data = fetch_templates_context()
    return jsonify(data)


@bp.route("/email-templates/api/save", methods=["POST"])
@_maybe_exempt
def api_email_templates_save():
    auth = _require_admin_json()
    if auth is not True:
        return auth
    payload = request.get_json(silent=True) or {}
    try:
        view = save_email_template(
            payload.get("template_key"),
            payload.get("language"),
            payload.get("html"),
            payload.get("subject"),
        )
    except TemplateValidationError as exc:
        return _json_error(str(exc), 400)
    return jsonify({
        "status": "saved",
        "template": {
            "key": view.key,
            "language": view.language,
            "subject": view.subject,
            "html": view.html_body,
            "updated_at": view.updated_at,
        },
    })


def register_ebookslv_blueprint(app):
    if not getattr(app, "_ebookslv_admin_bp", None):
        app.register_blueprint(bp)
        setattr(app, "_ebookslv_admin_bp", bp)


__all__ = ["register_ebookslv_blueprint", "bp"]
