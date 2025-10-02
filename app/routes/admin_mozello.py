"""Admin & webhook routes for Mozello notification integration.

Page: /admin/mozello
API:  /admin/mozello/settings (GET/PUT)
Webhook: /mozello/webhook (POST) – currently only logs PAYMENT_CHANGED
"""
from __future__ import annotations

from typing import Any, Dict, Optional

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

def _computed_webhook_url() -> Optional[str]:
    try:
        proto = request.headers.get("X-Forwarded-Proto", request.scheme)
        host = request.headers.get("X-Forwarded-Host", request.host)
        return f"{proto}://{host}/mozello/webhook"
    except Exception:  # pragma: no cover
        return None

@bp.route("/", methods=["GET"])  # UI page
def mozello_admin_page():  # pragma: no cover (thin render)
    auth = _require_admin()
    if auth is not True:
        return auth
    settings = mozello_service.get_settings()
    settings["notifications_url"] = _computed_webhook_url()
    return render_template("mozello_admin.html", mozello=settings, allowed=mozello_service.allowed_events())

@bp.route("/settings", methods=["GET"])
def mozello_get_settings():
    auth = _require_admin()
    if auth is not True:
        return auth
    data = mozello_service.get_settings()
    data["notifications_url"] = _computed_webhook_url()
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
    if events is not None and not isinstance(events, list):
        return jsonify({"error": "notifications_wanted must be list"}), 400
    updated = mozello_service.update_settings(api_key, None, events)
    updated["notifications_url"] = _computed_webhook_url()
    return jsonify(updated)

@webhook_bp.route("/mozello/webhook", methods=["POST"])
@_maybe_exempt
def mozello_webhook():
    raw = request.get_data()  # raw body for signature
    # Accept JSON only
    headers = {k: v for k, v in request.headers.items()}
    # Event value from payload handled in service (we pass placeholder)
    ok, msg = mozello_service.handle_webhook("", raw, headers)
    if not ok:
        LOG.warning("Mozello webhook rejected: %s", msg)
        return jsonify({"status": "rejected", "reason": msg}), 400
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
