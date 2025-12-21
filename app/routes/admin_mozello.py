"""Admin & webhook routes for Mozello notification integration.

Page: /admin/mozello
API:  /admin/mozello/settings (GET/PUT)
Webhook: /mozello/webhook (POST) – verifies Mozello signature and imports paid orders
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from flask import Blueprint, request, jsonify, render_template, redirect, abort, session
except Exception:  # pragma: no cover
    Blueprint = object  # type: ignore
    def request():  # type: ignore
        raise RuntimeError("Flask not available")
    def jsonify(*a, **k):  # type: ignore
        return {"error": "Flask missing"}, 500
        def redirect(*a, **k):  # type: ignore
            raise RuntimeError("Flask not available")
        def abort(*a, **k):  # type: ignore
            raise RuntimeError("Flask not available")

from app.utils import ensure_admin, PermissionError
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
    mozello_service,
    mozello_notifications_log_service,
    orders_service,
    OrderValidationError,
    CalibreUnavailableError,
    books_sync,
)
from app.utils.logging import get_logger
from app.i18n.preferences import SESSION_LOCALE_KEY

LOG = get_logger("mozello.routes")


def _request_language_code() -> Optional[str]:
    try:
        override = request.args.get("lang")
        if isinstance(override, str):
            override_clean = override.strip().lower()
            if override_clean in ("lv", "ru", "en"):
                return override_clean
    except Exception:
        pass
    try:  # pragma: no cover
        from flask_babel import get_locale  # type: ignore

        loc = get_locale()
        if loc:
            return str(loc)
    except Exception:
        pass
    try:
        raw = session.get(SESSION_LOCALE_KEY)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    except Exception:
        pass
    return None

bp = Blueprint("mozello_admin", __name__, url_prefix="/admin/mozello", template_folder="../templates")
webhook_bp = Blueprint("mozello_webhook", __name__)

_ALL_WEBHOOK_EVENTS = {event.upper() for event in mozello_service.allowed_events()}

_ERROR_MESSAGES = {
    "permission_denied": _("Administrator access required."),
    "mozello_settings_error": _("Unable to update Mozello settings."),
    "notifications_wanted_list": _("Events payload must be a list."),
}


def _json_error(code: str, status: int = 400, *, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
    payload: Dict[str, Any] = {"error": code}
    final = message or _ERROR_MESSAGES.get(code)
    if final:
        payload["message"] = final
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status

try:
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
        return _json_error("permission_denied", 403, message=str(exc))
    return True

def _computed_webhook_url() -> Optional[str]:
    """Compute candidate webhook URL using current request host.

    Historical behavior forced :80 so Mozello web UI could copy/paste the
    value during early HTTP-only deployments. After HTTPS migration we must
    *not* add an explicit port because Mozello will attempt a TLS handshake on
    the provided port and fail if it remains :80. Allow the upstream proxy to
    advertise whatever port it already includes; only append :80 when the
    request is plain HTTP and no port was specified.
    """
    try:
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host") or request.host
        if ":" not in host and proto == "http":
            host = f"{host}:80"
        return f"{proto}://{host}/mozello/webhook"
    except Exception:  # pragma: no cover
        return None

@bp.route("/", methods=["GET"])  # UI page
def mozello_admin_page():  # pragma: no cover (thin render)
    auth = _require_admin()
    if auth is not True:
        return auth
    # Conservative: do NOT call remote Mozello API here. Only compute candidate.
    candidate = _computed_webhook_url()
    ctx = {
        "notifications_url": candidate,
        "remote_notifications_url": None,
        "notifications_wanted": [],
        "remote_raw": None,
    }
    return render_template("mozello_admin.html", mozello=ctx, allowed=mozello_service.allowed_events())
@webhook_bp.route("/mozello/books/<path:mz_handle>", methods=["GET"])
def mozello_product_redirect(mz_handle: str):
    handle = (mz_handle or "").strip()
    if handle.isdigit():
        lookup = books_sync.get_mz_handle_for_book(int(handle))
        if lookup:
            handle = lookup.strip()
    if not handle:
        abort(404)

    relative_url = books_sync.get_mz_relative_url_for_handle(handle)

    # Prefer Mozello API language-specific URLs (when available). Fall back to stored
    # mz_relative_url (historically LV-only) to keep the link usable during API issues.
    target_url = mozello_service.resolve_product_storefront_url(
        handle,
        _request_language_code(),
        fallback_relative_url=relative_url,
    )
    if not target_url:
        if not relative_url:
            LOG.info("Mozello product redirect missing relative url handle=%s", handle)
            abort(404)
        LOG.warning("Mozello product redirect missing store url handle=%s", handle)
        abort(503)
    return redirect(target_url)


@bp.route("/product/<path:mz_handle>", methods=["GET"])
def mozello_debug_product(mz_handle: str):
    """Admin-only debug helper: fetch product JSON and show URL fields.

    This is intentionally a JSON endpoint (no UI) so admins can confirm whether
    Mozello returns different URLs per language.
    """
    auth = _require_admin()
    if auth is not True:
        return auth

    handle = (mz_handle or "").strip()
    if handle.isdigit():
        lookup = books_sync.get_mz_handle_for_book(int(handle))
        if lookup:
            handle = lookup.strip()
    if not handle:
        return _json_error("handle_required", 400, message="handle_required")

    ok, payload = mozello_service.fetch_product(handle)
    derived: Dict[str, Optional[str]] = {}
    absolute: Dict[str, Optional[str]] = {}
    if ok:
        for lang in ("lv", "ru", "en"):
            try:
                derived[lang] = mozello_service.derive_relative_url_from_product(payload, preferred_language=lang)
            except Exception:
                derived[lang] = None
            try:
                store_base = mozello_service.get_store_url(lang)
                value = derived.get(lang)
                if value and (value.startswith("http://") or value.startswith("https://")):
                    absolute[lang] = value
                elif value and store_base:
                    absolute[lang] = mozello_service._join_store_base_and_path(store_base, value)  # type: ignore[attr-defined]
                else:
                    absolute[lang] = None
            except Exception:
                absolute[lang] = None

    product = (
        payload.get("product")
        if ok and isinstance(payload.get("product"), dict)
        else (payload if ok and isinstance(payload, dict) else None)
    )
    url_field = product.get("url") if isinstance(product, dict) else None
    full_url_field = (product.get("full_url") or product.get("fullUrl")) if isinstance(product, dict) else None

    return jsonify(
        {
            "ok": ok,
            "handle": handle,
            "store_url": {
                "lv": mozello_service.get_store_url("lv"),
                "ru": mozello_service.get_store_url("ru"),
                "en": mozello_service.get_store_url("en"),
            },
            "product_url_field": url_field,
            "product_full_url_field": full_url_field,
            "derived_storefront_url": derived,
            "absolute_storefront_url": absolute,
            "response": payload,
        }
    )


@bp.route("/app_settings", methods=["GET"])
def mozello_get_app_settings():
    auth = _require_admin()
    if auth is not True:
        return auth
    return jsonify(mozello_service.get_app_settings())


@bp.route("/app_settings", methods=["PUT"])
@_maybe_exempt
def mozello_update_app_settings():
    auth = _require_admin()
    if auth is not True:
        return auth
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    try:
        updated = mozello_service.update_app_settings(
            store_url=data.get("mz_store_url"),
            store_url_lv=data.get("mz_store_url_lv"),
            store_url_ru=data.get("mz_store_url_ru"),
            store_url_en=data.get("mz_store_url_en"),
            api_key=data.get("mz_api_key"),
        )
    except RuntimeError as exc:
        return _json_error("mozello_settings_error", 503, message=str(exc))
    return jsonify(updated)

@bp.route("/settings", methods=["GET"])
def mozello_get_settings():
    auth = _require_admin()
    if auth is not True:
        return auth
    ok, remote = mozello_service.fetch_remote_notifications()
    candidate = _computed_webhook_url()
    data = {
        "notifications_url": candidate,
        "remote_notifications_url": (remote.get("notifications_url") if ok and isinstance(remote, dict) else None),
        "notifications_wanted": (remote.get("notifications_wanted") if ok and isinstance(remote, dict) else []),
        "remote_raw": remote,
        "remote_ok": ok,
    }
    return jsonify(data)

@bp.route("/settings", methods=["PUT"])
@_maybe_exempt
def mozello_update_settings():
    auth = _require_admin()
    if auth is not True:
        return auth
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    events = data.get("notifications_wanted") or []
    if not isinstance(events, list):
        return _json_error("notifications_wanted_list", 400)
    # Compute candidate URL (authoritative source now)
    candidate = _computed_webhook_url()
    ok_push, remote_after = mozello_service.push_remote_notifications(candidate, events)
    resp = {
        "notifications_url": candidate,
        "push_ok": ok_push,
        "remote_after": remote_after,
    }
    return jsonify(resp), (200 if ok_push else 400)

# Removed /sync route – syncing now implicit via live GET/PUT remote operations

@webhook_bp.route("/mozello/webhook", methods=["POST"])
@_maybe_exempt
def mozello_webhook():
    raw = request.get_data()
    headers = {k: v for k, v in request.headers.items()}
    ok, event_name, payload = mozello_service.handle_webhook(raw, headers)
    if not ok:
        LOG.warning("Mozello webhook rejected reason=%s remote=%s", event_name, getattr(request, "remote_addr", None))
        return jsonify({"status": "rejected", "reason": event_name}), 400

    event_upper = (event_name or "").upper()
    data = payload if isinstance(payload, dict) else {}
    order_data = data.get("order") if isinstance(data.get("order"), dict) else None

    def _maybe_log(outcome: str) -> None:
        try:
            mozello_notifications_log_service.append_log(
                event=event_upper,
                outcome=outcome,
                payload_raw=mozello_notifications_log_service.coerce_payload_to_text(raw),
            )
        except Exception:
            # Never break webhook processing due to logging.
            LOG.debug("Mozello notifications log append failed", exc_info=True)

    _dump_webhook_event(event_upper, data or {}, raw)

    if event_upper == "PRODUCT_CHANGED":
        product_data = data.get("product") if isinstance(data.get("product"), dict) else None
        if not product_data:
            LOG.warning("Mozello webhook PRODUCT_CHANGED missing product payload")
            _maybe_log("Rejected: PRODUCT_CHANGED missing product payload")
            return jsonify({"status": "rejected", "reason": "product_missing"}), 400
        product_handle = (product_data.get("handle") or "").strip()
        if not product_handle:
            LOG.warning("Mozello webhook PRODUCT_CHANGED missing product handle")
            _maybe_log("Rejected: PRODUCT_CHANGED missing product handle")
            return jsonify({"status": "rejected", "reason": "handle_missing"}), 400
        book_info = books_sync.lookup_book_by_handle(product_handle)
        preferred_language = book_info.get("language_code") if isinstance(book_info, dict) else None

        # Persist Mozello pictures list (uid+url) for later use.
        raw_pictures = product_data.get("pictures")
        stored_pictures = False
        if isinstance(raw_pictures, list):
            stored_pictures = books_sync.set_mz_pictures_for_handle(product_handle, raw_pictures)

        # If we don't yet know which Mozello picture is the Calibre cover, default to the first Mozello picture.
        # This is used only to track which picture to replace on future Calibre->Mozello exports.
        cover_seeded = False
        try:
            existing_cover = books_sync.get_mz_cover_picture_uids_for_handle(product_handle)
        except Exception:
            existing_cover = []
        if not existing_cover and isinstance(raw_pictures, list) and raw_pictures:
            first = raw_pictures[0] if isinstance(raw_pictures[0], dict) else None
            first_uid = (first.get("uid") if isinstance(first, dict) else None)
            if isinstance(first_uid, str) and first_uid.strip():
                cover_seeded = bool(books_sync.set_mz_cover_picture_uids_for_handle(product_handle, [first_uid.strip()]))

        relative_url = mozello_service.derive_relative_url_from_product(
            product_data,
            preferred_language=preferred_language,
            force_refresh=True,
        )
        stored_relative = False
        if relative_url:
            stored_relative = books_sync.set_mz_relative_url_for_handle(product_handle, relative_url)
        else:
            books_sync.clear_mz_relative_url_for_handle(product_handle)
        # Sync Mozello price into Calibre if the custom column exists
        price_value = product_data.get("price")
        if product_data.get("sale_price") is not None:
            price_value = product_data.get("sale_price")
        stored_price = books_sync.set_mz_price_for_handle(product_handle, price_value)

        if stored_relative or stored_price:
            _maybe_log(f"Book '{product_handle}' was updated")
        else:
            _maybe_log(f"Product '{product_handle}' received; no local book updated")

        response_payload = {
            "status": "ok",
            "event": event_upper,
            "mz_handle": product_handle,
        }
        if relative_url:
            response_payload["mz_relative_url"] = relative_url
        response_payload["relative_url_stored"] = bool(stored_relative)
        response_payload["price_stored"] = bool(stored_price)
        response_payload["pictures_stored"] = bool(stored_pictures)
        response_payload["cover_seeded"] = bool(cover_seeded)
        return jsonify(response_payload)

    if event_upper != "PAYMENT_CHANGED":
        LOG.debug("Mozello webhook ignoring event=%s", event_upper)
        _maybe_log(f"Ignored event '{event_upper}'")
        return jsonify({"status": "ignored", "reason": "event_ignored", "event": event_upper}), 200

    if not isinstance(order_data, dict):
        LOG.warning("Mozello webhook missing order payload event=%s", event_upper)
        _maybe_log("Rejected: PAYMENT_CHANGED missing order payload")
        return jsonify({"status": "rejected", "reason": "order_missing"}), 400

    payment_status = str(order_data.get("payment_status") or "").strip().lower()
    if payment_status != "paid":
        LOG.info(
            "Mozello webhook skipping order payment_status=%s order_id=%s",
            payment_status,
            order_data.get("order_id"),
        )
        _maybe_log(f"Ignored order payment_status='{payment_status or ''}'")
        return jsonify({
            "status": "ignored",
            "reason": "payment_status",
            "payment_status": order_data.get("payment_status"),
        }), 200

    try:
        result = orders_service.process_webhook_order(order_data)
    except OrderValidationError as exc:
        LOG.warning(
            "Mozello webhook order validation failed order_id=%s error=%s",
            order_data.get("order_id"),
            exc,
        )
        _maybe_log(f"Rejected order: {str(exc)}")
        return jsonify({"status": "rejected", "reason": str(exc)}), 400
    except CalibreUnavailableError as exc:
        LOG.error(
            "Mozello webhook Calibre unavailable order_id=%s email=%s error=%s",
            order_data.get("order_id"),
            order_data.get("email"),
            exc,
        )
        _maybe_log("Retry: Calibre unavailable")
        return jsonify({"status": "retry", "reason": "calibre_unavailable"}), 503
    except Exception as exc:  # pragma: no cover - defensive
        LOG.exception(
            "Mozello webhook processing failure order_id=%s",
            order_data.get("order_id"),
        )
        _maybe_log("Error: internal_error")
        return jsonify({"status": "error", "reason": "internal_error"}), 500

    order_id = order_data.get("order_id")
    _maybe_log(f"Paid order processed (order_id={order_id})")

    return jsonify({"status": "ok", "result": result})


@bp.route("/notifications_log", methods=["GET"])
def mozello_get_notifications_log():
    auth = _require_admin()
    if auth is not True:
        return auth
    try:
        limit_raw = request.args.get("limit")
        limit = int(limit_raw) if isinstance(limit_raw, str) and limit_raw.strip().isdigit() else 50
    except Exception:
        limit = 50
    return jsonify(mozello_notifications_log_service.get_state(limit=limit))


@bp.route("/notifications_log", methods=["PUT"])
@_maybe_exempt
def mozello_update_notifications_log_settings():
    auth = _require_admin()
    if auth is not True:
        return auth
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    enabled = bool(data.get("enabled"))
    try:
        new_value = mozello_notifications_log_service.set_enabled(enabled)
    except Exception as exc:
        return _json_error("mozello_settings_error", 503, message=str(exc))
    return jsonify({"enabled": bool(new_value)})


@bp.route("/notifications_log", methods=["DELETE"])
@_maybe_exempt
def mozello_clear_notifications_log():
    auth = _require_admin()
    if auth is not True:
        return auth
    try:
        deleted = mozello_notifications_log_service.clear_logs()
    except Exception as exc:
        return _json_error("mozello_settings_error", 503, message=str(exc))
    return jsonify({"cleared": deleted})

def register_blueprints(app):
    if not getattr(app, "_mozello_admin_bp", None):
        app.register_blueprint(bp)
        setattr(app, "_mozello_admin_bp", bp)
    if not getattr(app, "_mozello_webhook_bp", None):
        app.register_blueprint(webhook_bp)
        setattr(app, "_mozello_webhook_bp", webhook_bp)
    # Exempt after registration
    if csrf:  # type: ignore
        try:
            csrf.exempt(webhook_bp)  # type: ignore[arg-type]
            csrf.exempt(mozello_webhook)
            csrf.exempt(mozello_update_settings)
            csrf.exempt(mozello_update_app_settings)
        except Exception:
            pass

__all__ = ["register_blueprints"]


def _dump_webhook_event(event: str, payload: Dict[str, Any], raw_body: bytes) -> None:
    """Persist webhook payload to disk when dump path configured."""
    dump_root = os.getenv("MOZELLO_WEBHOOK_DUMP_PATH", "").strip()
    if not dump_root:
        return
    if event.upper() not in _ALL_WEBHOOK_EVENTS:
        return
    try:
        os.makedirs(dump_root, exist_ok=True)
        safe_event = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in (event or "UNKNOWN")) or "UNKNOWN"
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%f")
        file_path = os.path.join(dump_root, f"{safe_event}_{timestamp}.json")
        dump_payload = {
            "event": event or "UNKNOWN",
            "received_at": datetime.utcnow().isoformat() + "Z",
            "payload": payload,
            "raw_body": raw_body.decode("utf-8", errors="replace"),
        }
        with open(file_path, "w", encoding="utf-8") as handle:
            json.dump(dump_payload, handle, indent=2, sort_keys=True)
    except Exception:  # pragma: no cover - defensive dump guard
        LOG.warning("Failed dumping Mozello webhook event=%s", event or "UNKNOWN", exc_info=True)
