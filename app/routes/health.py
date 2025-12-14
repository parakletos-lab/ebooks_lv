"""Lightweight health probe endpoint.

Exposes /healthz returning a fast 200 for container / LB health checks.
Per Agent Rules: uses logging helper and avoids raw os.environ inside logic.
"""
from __future__ import annotations

from typing import Any

try:
    from flask import Blueprint, jsonify
except Exception:  # pragma: no cover
    Blueprint = object  # type: ignore
    def jsonify(obj: Any):  # type: ignore
        return obj

from app.utils.logging import get_logger
from app.db.engine import app_session
from sqlalchemy import text

LOG = get_logger("health")

bp = Blueprint("health", __name__)


@bp.route("/healthz", methods=["GET"])  # simple, cache-friendly
def healthz():  # pragma: no cover (trivial)
    # Try a trivial DB round-trip (optional, fast) to increase confidence.
    db_ok = True
    try:
        with app_session() as s:
            s.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        db_ok = False
        LOG.debug("Health DB probe failed: %s", exc)
    status_code = 200 if db_ok else 500
    return jsonify({"status": "ok" if db_ok else "degraded", "db": db_ok}), status_code


def register_health(app: Any) -> None:
    if getattr(app, "_health_bp", None):  # idempotent
        return
    try:
        app.register_blueprint(bp)  # type: ignore[attr-defined]
        setattr(app, "_health_bp", bp)
        LOG.debug("health blueprint registered")
    except Exception as exc:  # pragma: no cover
        LOG.debug("Failed registering health blueprint: %s", exc)


__all__ = ["register_health"]
