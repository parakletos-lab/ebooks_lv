"""Mozello integration service layer.

Responsibilities:
  * Persist & fetch API key + notification settings (single-row table)
  * Provide allowed event list
  * Handle inbound webhook verification (PAYMENT_CHANGED etc.)
"""
from __future__ import annotations

from typing import List, Tuple, Optional, Dict, Any
import hmac, hashlib, base64, json
from sqlalchemy import text

from app.db.engine import app_session
from app.db.models import MozelloConfig
from app.utils.logging import get_logger

LOG = get_logger("mozello.mozello_service")


def _get_singleton(create: bool = True) -> MozelloConfig:
    _ensure_schema_migrations()
    with app_session() as s:
        obj = s.get(MozelloConfig, 1)
        if obj is None and create:
            obj = MozelloConfig(id=1)
            s.add(obj)
        # session commits on context exit
    # re-open to get refreshed state
    with app_session() as s2:
        return s2.get(MozelloConfig, 1)  # type: ignore


def get_settings() -> Dict[str, Any]:
    cfg = _get_singleton(create=True)
    return cfg.as_dict()


def update_settings(api_key: Optional[str], notifications_url: Optional[str], events: Optional[List[str]], forced_port: Optional[str] = None) -> Dict[str, Any]:
    with app_session() as s:
        cfg = s.get(MozelloConfig, 1)
        if cfg is None:
            cfg = MozelloConfig(id=1)
            s.add(cfg)
        if api_key is not None:
            cfg.api_key = api_key.strip() or None
        # notifications_url now computed dynamically; ignore writes unless explicitly provided (migration support)
        if notifications_url:
            cfg.notifications_url = notifications_url.strip() or None
        if events is not None:
            cfg.set_events(events)
        if forced_port is not None:
            cfg.forced_port = (forced_port.strip() or None)
        LOG.info("Mozello settings updated url=%s events=%s api_key_set=%s", cfg.notifications_url, cfg.events_list(), bool(cfg.api_key))
    return get_settings()


def allowed_events() -> List[str]:
    return list(MozelloConfig.ALLOWED_EVENTS)


def verify_signature(raw_body: bytes, provided_hash: str, api_key: str) -> bool:
    expected = base64.b64encode(hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode()
    try:
        return hmac.compare_digest(expected, provided_hash or "")
    except Exception:
        return False


def handle_webhook(event: str, raw_body: bytes, headers: Dict[str, str]) -> Tuple[bool, str]:
    """Process inbound Mozello webhook.

    For now we just log PAYMENT_CHANGED events. Returns (accepted, message).
    """
    cfg = _get_singleton()
    if not cfg.api_key:
        return False, "api_key_not_configured"
    provided = headers.get("X-Mozello-Hash") or headers.get("x-mozello-hash", "")
    # Allow explicit local test bypass (not sent by Mozello) only if header present
    if headers.get("X-Mozello-Test", "").lower() == "unsigned" and provided == "":
        pass
    else:
        if not verify_signature(raw_body, provided, cfg.api_key):
            return False, "signature_invalid"
    # Parse JSON (defensive)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False, "invalid_json"
    evt = payload.get("event") or event
    if evt == "PAYMENT_CHANGED":
        LOG.info("Mozello PAYMENT_CHANGED received: %s", payload)
    else:
        LOG.debug("Mozello event received (ignored for now): %s", evt)
    return True, "ok"

__all__ = [
    "get_settings",
    "update_settings",
    "allowed_events",
    "handle_webhook",
]


def _get_api_key_raw() -> Optional[str]:
    try:
        cfg = _get_singleton(create=True)
        return cfg.api_key
    except Exception:  # pragma: no cover
        return None

__all__.append("_get_api_key_raw")


# --------------------- Lightweight Lazy Migrations ---------------------

_SCHEMA_CHECKED = False

def _ensure_schema_migrations():  # pragma: no cover (best-effort, simple)
    global _SCHEMA_CHECKED
    if _SCHEMA_CHECKED:
        return
    try:
        with app_session() as s:
            cols = [row[1] for row in s.execute(text("PRAGMA table_info(mozello_config)"))]
            if "forced_port" not in cols:
                LOG.warning("Applying schema migration: adding mozello_config.forced_port column")
                s.execute(text("ALTER TABLE mozello_config ADD COLUMN forced_port VARCHAR(10)"))
    except Exception as exc:
        LOG.error("Mozello schema migration check failed: %s", exc)
    finally:
        _SCHEMA_CHECKED = True

__all__.append("_ensure_schema_migrations")
