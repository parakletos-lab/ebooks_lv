"""Mozello integration service layer.

Responsibilities:
  * Persist & fetch API key + notification settings (single-row table)
  * Provide allowed event list
  * Handle inbound webhook verification (PAYMENT_CHANGED etc.)
"""
from __future__ import annotations

from typing import List, Tuple, Optional, Dict, Any
import hmac, hashlib, base64, json, time
from sqlalchemy import text
import requests
from app import config

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
    # forced_port persistence deprecated (no longer used for webhook URL)
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


# --------------------- Outbound Mozello Sync ---------------------------

def _api_headers() -> Dict[str, str]:
    key = config.mozello_api_key() or ""
    if not key:
        return {}
    # Mozello spec: Authorization: ApiKey <KEY>
    return {
        "Authorization": f"ApiKey {key}",
        "Accept": "application/json",
        "User-Agent": "ebooks-lv-integrator/1.0"
    }

def fetch_remote_notifications(timeout: int = 10) -> Tuple[bool, Dict[str, Any]]:
    base = config.mozello_api_base().rstrip('/')
    try:
        headers = _api_headers()
        if not headers:
            return False, {"error": "api_key_missing"}
        r = requests.get(f"{base}/store/notifications/", headers=headers, timeout=timeout)
        status = r.status_code
        text_body = r.text
        # Attempt JSON parsing regardless of status
        try:
            data = r.json()
        except Exception:
            data = {"raw": text_body}
        if status == 401:
            return False, {"error": "unauthorized", "details": data}
        if status != 200:
            return False, {"error": "http_error", "status": status, "details": data}
        # Mozello success contract may include error=false
        if isinstance(data, dict) and data.get("error") is True:
            return False, {"error": "remote_error", "details": data}
        return True, data  # expected shape: notifications_url + notifications_wanted
    except Exception as exc:
        LOG.warning("Mozello fetch_remote_notifications failed: %s", exc)
        return False, {"error": str(exc)}

def push_remote_notifications(url: Optional[str], events: List[str], timeout: int = 10) -> Tuple[bool, Dict[str, Any]]:
    base = config.mozello_api_base().rstrip('/')
    body = {"notifications_url": url, "notifications_wanted": events}
    try:
        headers = _api_headers()
        if not headers:
            return False, {"error": "api_key_missing"}
        r = requests.put(f"{base}/store/notifications/", json=body, headers=headers, timeout=timeout)
        status = r.status_code
        text_body = r.text
        try:
            data = r.json()
        except Exception:
            data = {"raw": text_body}
        if status == 401:
            return False, {"error": "unauthorized", "details": data}
        if status != 200:
            return False, {"error": "http_error", "status": status, "details": data}
        if isinstance(data, dict) and data.get("error") is True:
            return False, {"error": "remote_error", "details": data}
        return True, data
    except Exception as exc:
        LOG.warning("Mozello push_remote_notifications failed: %s", exc)
        return False, {"error": str(exc)}

def sync_now(local_url: Optional[str], local_events: List[str]) -> Dict[str, Any]:
    """Full sync: fetch remote, compare, push if drift.

    Returns dict with keys: remote_before, pushed, remote_after (optional), diff
    """
    started = time.time()
    ok_fetch, remote_before = fetch_remote_notifications()
    diff = {}
    pushed = False
    remote_after: Dict[str, Any] | None = None
    if ok_fetch and isinstance(remote_before, dict):
        rb_url = remote_before.get("notifications_url")
        rb_events = remote_before.get("notifications_wanted") or []
        if rb_url != local_url:
            diff["url"] = {"remote": rb_url, "local": local_url}
        if sorted(rb_events) != sorted(local_events):
            diff["events"] = {"remote": rb_events, "local": local_events}
        if diff:
            ok_push, remote_after = push_remote_notifications(local_url, local_events)
            pushed = ok_push
    duration = round(time.time() - started, 3)
    return {
        "duration_sec": duration,
        "remote_before": remote_before,
        "pushed": pushed,
        "diff": diff,
        "remote_after": remote_after,
    }

__all__.extend([
    "fetch_remote_notifications",
    "push_remote_notifications",
    "sync_now",
])
