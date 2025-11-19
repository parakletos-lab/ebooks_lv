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
    from flask import Blueprint, request, jsonify, render_template, redirect, abort
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
from app.services import (
    mozello_service,
    orders_service,
    OrderValidationError,
    CalibreUnavailableError,
    books_sync,
)
from app.utils.logging import get_logger

LOG = get_logger("mozello.routes")

bp = Blueprint("mozello_admin", __name__, url_prefix="/admin/mozello", template_folder="../templates")
webhook_bp = Blueprint("mozello_webhook", __name__)

_ALL_WEBHOOK_EVENTS = {event.upper() for event in mozello_service.allowed_events()}

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
        return jsonify({"error": str(exc)}), 403
    return True

def _computed_webhook_url() -> Optional[str]:
    """Compute candidate webhook URL using current request host.

    If no explicit port in host, append :80 (per user preference) even if
    default for http/https. No local persistence.
    """
    try:
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host") or request.host
        if ":" not in host:
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
    if not relative_url:
        LOG.info("Mozello product redirect missing relative url handle=%s", handle)
        abort(404)

    store_base = mozello_service.get_store_url()
    if not store_base:
        LOG.warning("Mozello store URL not configured for redirect handle=%s", handle)
        abort(503)

    normalized_relative = "/" + relative_url.lstrip("/")
    target_url = f"{store_base.rstrip('/')}{normalized_relative}"
    return redirect(target_url)


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
            api_key=data.get("mz_api_key"),
        )
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
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
        return jsonify({"error": "notifications_wanted must be list"}), 400
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

    _dump_webhook_event(event_upper, data or {}, raw)

    if event_upper == "PRODUCT_CHANGED":
        product_data = data.get("product") if isinstance(data.get("product"), dict) else None
        if not product_data:
            LOG.warning("Mozello webhook PRODUCT_CHANGED missing product payload")
            return jsonify({"status": "rejected", "reason": "product_missing"}), 400
        product_handle = (product_data.get("handle") or "").strip()
        if not product_handle:
            LOG.warning("Mozello webhook PRODUCT_CHANGED missing product handle")
            return jsonify({"status": "rejected", "reason": "handle_missing"}), 400
        book_info = books_sync.lookup_book_by_handle(product_handle)
        preferred_language = book_info.get("language_code") if isinstance(book_info, dict) else None
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
        response_payload = {
            "status": "ok",
            "event": event_upper,
            "mz_handle": product_handle,
        }
        if relative_url:
            response_payload["mz_relative_url"] = relative_url
        response_payload["relative_url_stored"] = bool(stored_relative)
        return jsonify(response_payload)

    if event_upper != "PAYMENT_CHANGED":
        LOG.debug("Mozello webhook ignoring event=%s", event_upper)
        return jsonify({"status": "ignored", "reason": "event_ignored", "event": event_upper}), 200

    if not isinstance(order_data, dict):
        LOG.warning("Mozello webhook missing order payload event=%s", event_upper)
        return jsonify({"status": "rejected", "reason": "order_missing"}), 400

    payment_status = str(order_data.get("payment_status") or "").strip().lower()
    if payment_status != "paid":
        LOG.info(
            "Mozello webhook skipping order payment_status=%s order_id=%s",
            payment_status,
            order_data.get("order_id"),
        )
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
        return jsonify({"status": "rejected", "reason": str(exc)}), 400
    except CalibreUnavailableError as exc:
        LOG.error(
            "Mozello webhook Calibre unavailable order_id=%s email=%s error=%s",
            order_data.get("order_id"),
            order_data.get("email"),
            exc,
        )
        return jsonify({"status": "retry", "reason": "calibre_unavailable"}), 503
    except Exception as exc:  # pragma: no cover - defensive
        LOG.exception(
            "Mozello webhook processing failure order_id=%s",
            order_data.get("order_id"),
        )
        return jsonify({"status": "error", "reason": "internal_error"}), 500

    return jsonify({"status": "ok", "result": result})

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
