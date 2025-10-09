"""Admin & webhook routes for Mozello notification integration.

Page: /admin/mozello
API:  /admin/mozello/settings (GET/PUT)
Webhook: /mozello/webhook (POST) – currently only logs PAYMENT_CHANGED
"""
from __future__ import annotations

from typing import Any, Dict, Optional
import os, json, base64, traceback
from datetime import datetime

try:
    from flask import Blueprint, request, jsonify, render_template
except Exception:  # pragma: no cover
    Blueprint = object  # type: ignore
    def request():  # type: ignore
        raise RuntimeError("Flask not available")
    def jsonify(*a, **k):  # type: ignore
        return {"error": "Flask missing"}, 500

from app.utils import ensure_admin, PermissionError
from app.services import mozello_service
from app.utils.logging import get_logger

LOG = get_logger("mozello.routes")

bp = Blueprint("mozello_admin", __name__, url_prefix="/admin/mozello", template_folder="../templates")
webhook_bp = Blueprint("mozello_webhook", __name__)

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

def _computed_webhook_url(forced_port: Optional[str] = None) -> Optional[str]:
    try:
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host") or request.host
        if forced_port:
            if ':' in host:
                host_only = host.split(':', 1)[0]
            else:
                host_only = host
            host = f"{host_only}:{forced_port}"
        return f"{proto}://{host}/mozello/webhook"
    except Exception:  # pragma: no cover
        return None

@bp.route("/", methods=["GET"])  # UI page
def mozello_admin_page():  # pragma: no cover (thin render)
    auth = _require_admin()
    if auth is not True:
        return auth
    settings = mozello_service.get_settings()
    settings["notifications_url"] = _computed_webhook_url(settings.get("forced_port"))
    return render_template("mozello_admin.html", mozello=settings, allowed=mozello_service.allowed_events())

@bp.route("/settings", methods=["GET"])
def mozello_get_settings():
    auth = _require_admin()
    if auth is not True:
        return auth
    data = mozello_service.get_settings()
    data["notifications_url"] = _computed_webhook_url(data.get("forced_port"))
    return jsonify(data)

@bp.route("/settings", methods=["PUT"])
@_maybe_exempt
def mozello_update_settings():
    auth = _require_admin()
    if auth is not True:
        return auth
    data: Dict[str, Any] = request.get_json(silent=True) or {}
    api_key = data.get("api_key")
    # notifications_url is auto-computed; ignore any client-provided value
    events = data.get("notifications_wanted")
    forced_port = data.get("forced_port")
    if events is not None and not isinstance(events, list):
        return jsonify({"error": "notifications_wanted must be list"}), 400
    updated = mozello_service.update_settings(api_key, None, events, forced_port)
    updated["notifications_url"] = _computed_webhook_url(updated.get("forced_port"))
    return jsonify(updated)

@webhook_bp.route("/mozello/webhook", methods=["POST"])
@_maybe_exempt
def mozello_webhook():
    ts = datetime.utcnow()
    ts_tag = ts.strftime('%Y%m%dT%H%M%S%fZ')
    raw = request.get_data()  # raw body for signature
    headers = {k: v for k, v in request.headers.items()}
    remote = getattr(request, 'remote_addr', None)
    dump_dir = os.path.join('config', 'mozello_webhook')  # segregate debug artifacts
    os.makedirs(dump_dir, exist_ok=True)

    debug_record: Dict[str, Any] = {
        "timestamp": ts.isoformat() + 'Z',
        "remote_addr": remote,
        "method": request.method,
        "path": request.path,
        "headers": headers,
        "raw_length": len(raw),
    }

    # Try decode raw body (text & parsed JSON) – do not trust encoding
    try:
        decoded = raw.decode('utf-8')
        debug_record["raw_text"] = decoded
        try:
            debug_record["json_payload"] = json.loads(decoded)
        except Exception as e:  # not valid JSON
            debug_record["json_error"] = str(e)
    except Exception as e:  # pragma: no cover
        debug_record["decode_error"] = str(e)
        debug_record["raw_b64"] = base64.b64encode(raw).decode('ascii')

    service_ok = False
    service_msg = "unprocessed"
    try:
        service_ok, service_msg = mozello_service.handle_webhook("", raw, headers)
        debug_record["service_ok"] = service_ok
        debug_record["service_msg"] = service_msg
    except Exception as e:  # pragma: no cover
        debug_record["service_exception"] = str(e)
        debug_record["service_traceback"] = traceback.format_exc()
        LOG.exception("Mozello webhook internal error")

    # Persist structured record (even if service failed)
    try:
        dump_path = os.path.join(dump_dir, f"mozello_webhook_{ts_tag}.json")
        with open(dump_path, 'w', encoding='utf-8') as f:
            json.dump(debug_record, f, ensure_ascii=False, indent=2, sort_keys=True)
        LOG.info("Mozello webhook debug record saved %s service_ok=%s", dump_path, service_ok)
    except Exception:  # pragma: no cover
        LOG.exception("Failed to write mozello webhook debug record")

    if not service_ok:
        return jsonify({"status": "rejected", "reason": service_msg}), 400
    return jsonify({"status": "ok"})

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
        except Exception:
            pass

__all__ = ["register_blueprints"]
