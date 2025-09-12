"""
routes_metrics.py

Metrics endpoint(s) for the users_books plugin.

Primary Endpoint (registered under /plugin/users_books):
    GET /metrics
        - Returns aggregate counts about current allow‑list mappings.
        - Only available when USERS_BOOKS_ENABLE_METRICS is truthy.
        - Requires admin privileges (session['is_admin'] == True).
        - Response (200):
            {
              "plugin": "users_books",
              "version": "<semver>",
              "metrics": {
                "total_mappings": <int>,
                "distinct_users": <int>,
                "distinct_books": <int>
              }
            }

Optional Diagnostic Endpoint:
    GET /metrics/runtime
        - Also requires admin + metrics enabled.
        - Returns a snapshot of non-sensitive runtime configuration to aid debugging.

Common Error Responses:
    403 {"error": "Admin privileges required"}
    404 {"error": "Metrics disabled"} (when feature not enabled)
    500 {"error": "Internal error"} (rare unexpected failure)

Design Notes:
    - All data is gathered via services.* helpers (no raw SQL here).
    - Admin guard performed via utils.ensure_admin().
    - Configuration gating via config.metrics_enabled().
    - Safe failures: if metrics disabled we return 404 to avoid advertising an inactive endpoint.

Extensibility:
    - Add latency / performance counters once internal instrumentation exists.
    - Emit Prometheus-compatible exposition format at a separate endpoint if needed.
"""

from __future__ import annotations

from flask import jsonify

from .. import config, services, utils
from ..utils import PermissionError
from ..logging_setup import get_logger

LOG = get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _require_metrics_enabled():
    if not config.metrics_enabled():
        return _json_error("Metrics disabled", 404)
    return True


def _require_admin():
    try:
        utils.ensure_admin()
        return True
    except PermissionError as exc:
        return _json_error(str(exc), 403)


# ---------------------------------------------------------------------------
# Route Registration
# ---------------------------------------------------------------------------

def register(bp):
    """
    Register metrics-related routes onto the provided Blueprint.
    """

    @bp.route("/metrics", methods=["GET"])
    def metrics_root():
        # Feature gate
        enabled = _require_metrics_enabled()
        if enabled is not True:
            return enabled  # (response, status)

        # Admin only
        admin_ok = _require_admin()
        if admin_ok is not True:
            return admin_ok  # (response, status)

        try:
            snapshot = services.metrics_snapshot()
        except Exception as exc:  # pragma: no cover - defensive
            LOG.error("Failed to collect metrics: %s", exc, exc_info=True)
            return _json_error("Internal error", 500)

        return jsonify({
            "plugin": config.PLUGIN_NAME,
            "version": config.PLUGIN_VERSION,
            "metrics": snapshot,
        })

    @bp.route("/metrics/runtime", methods=["GET"])
    def metrics_runtime():
        # Feature gate
        enabled = _require_metrics_enabled()
        if enabled is not True:
            return enabled

        # Admin only
        admin_ok = _require_admin()
        if admin_ok is not True:
            return admin_ok

        try:
            runtime_cfg = config.summarize_runtime_config()
        except Exception as exc:  # pragma: no cover
            LOG.error("Failed to summarize runtime config: %s", exc, exc_info=True)
            return _json_error("Internal error", 500)

        return jsonify({
            "plugin": config.PLUGIN_NAME,
            "version": config.PLUGIN_VERSION,
            "runtime_config": runtime_cfg,
        })


__all__ = ["register"]
