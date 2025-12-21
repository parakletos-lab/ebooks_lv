"""Mozello webhook notifications logging.

Stores a rolling log of accepted webhook payloads for admin diagnostics.
Logging can be toggled on/off via a persisted flag in users_books DB.

Rules:
- Use service layer (this module).
- Invalidate cache after mutations.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select

from app.db.engine import app_session
from app.db.models import MozelloConfig, MozelloNotificationLog
from app.utils.logging import get_logger

LOG = get_logger("mozello.notifications_log")

# Simple in-process cache to reduce repetitive DB reads on admin page refresh.
_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {
    "enabled": None,
    "logs": None,
}


def invalidate_cache() -> None:
    with _CACHE_LOCK:
        # Clear all cached variants (e.g. logs:50) so mutations are visible.
        _CACHE.clear()
        _CACHE["enabled"] = None
        _CACHE["logs"] = None


def is_enabled() -> bool:
    with _CACHE_LOCK:
        cached = _CACHE.get("enabled")
    if isinstance(cached, bool):
        return cached

    try:
        with app_session() as s:
            cfg = s.get(MozelloConfig, 1)
            enabled = bool(getattr(cfg, "notifications_log_enabled", 0)) if cfg else False
    except Exception:
        LOG.warning("Failed reading notifications_log_enabled", exc_info=True)
        enabled = False

    with _CACHE_LOCK:
        _CACHE["enabled"] = enabled
    return enabled


def set_enabled(enabled: bool) -> bool:
    value = bool(enabled)
    try:
        with app_session() as s:
            cfg = s.get(MozelloConfig, 1)
            if cfg is None:
                cfg = MozelloConfig(id=1)
                s.add(cfg)
            setattr(cfg, "notifications_log_enabled", 1 if value else 0)
    except Exception:
        LOG.warning("Failed updating notifications_log_enabled enabled=%s", value, exc_info=True)
        raise
    invalidate_cache()
    return value


def append_log(*, event: str, outcome: str, payload_raw: Optional[str]) -> Optional[int]:
    if not is_enabled():
        return None

    evt = (event or "").strip().upper() or "UNKNOWN"
    out = (outcome or "").strip() or "(no outcome)"
    raw_text = payload_raw if isinstance(payload_raw, str) else None

    # Ensure payload is JSON-ish text; fall back to JSON dump when given a dict later.
    if raw_text is None:
        raw_text = ""

    try:
        with app_session() as s:
            row = MozelloNotificationLog(
                received_at=datetime.utcnow(),
                event=evt,
                outcome=out,
                payload_json=raw_text,
            )
            s.add(row)
            # flush to get id
            s.flush()
            new_id = int(row.id) if row.id is not None else None
    except Exception:
        LOG.warning("Failed appending Mozello notification log event=%s", evt, exc_info=True)
        return None

    invalidate_cache()
    return new_id


def list_logs(limit: int = 50) -> List[Dict[str, Any]]:
    safe_limit = int(limit) if isinstance(limit, int) else 50
    if safe_limit <= 0:
        safe_limit = 50
    if safe_limit > 500:
        safe_limit = 500

    cache_key = f"logs:{safe_limit}"
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
    if isinstance(cached, list):
        return cached

    try:
        with app_session() as s:
            rows = (
                s.execute(
                    select(MozelloNotificationLog)
                    .order_by(MozelloNotificationLog.received_at.desc(), MozelloNotificationLog.id.desc())
                    .limit(safe_limit)
                )
                .scalars()
                .all()
            )
    except Exception:
        LOG.warning("Failed listing Mozello notification logs", exc_info=True)
        rows = []

    result: List[Dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": row.id,
                "received_at": row.received_at.isoformat() + "Z" if row.received_at else None,
                "event": row.event,
                "outcome": row.outcome,
                "payload_json": row.payload_json or "",
            }
        )

    with _CACHE_LOCK:
        _CACHE[cache_key] = result
    return result


def clear_logs() -> int:
    try:
        with app_session() as s:
            res = s.execute(delete(MozelloNotificationLog))
            deleted = int(res.rowcount or 0)
    except Exception:
        LOG.warning("Failed clearing Mozello notification logs", exc_info=True)
        raise
    invalidate_cache()
    return deleted


def get_state(limit: int = 50) -> Dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "logs": list_logs(limit=limit),
    }


def coerce_payload_to_text(payload: Any) -> str:
    """Best-effort JSON serialization for storage."""
    if isinstance(payload, (bytes, bytearray)):
        try:
            return bytes(payload).decode("utf-8", errors="replace")
        except Exception:
            return ""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except Exception:
        try:
            return str(payload)
        except Exception:
            return ""
