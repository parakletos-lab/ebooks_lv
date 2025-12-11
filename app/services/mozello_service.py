"""Mozello integration service layer.

Responsibilities:
    * Persist & fetch API key + notification settings (single-row table)
    * Provide allowed event list
    * Handle inbound webhook verification (PAYMENT_CHANGED etc.)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Any, Set, Iterable
import hmac, hashlib, base64, json, time, threading
from datetime import datetime
from urllib.parse import quote_plus
from sqlalchemy import text
import requests
from app import config

from app.db.engine import app_session
from app.db.models import MozelloConfig
from app.utils.logging import get_logger

LOG = get_logger("mozello.mozello_service")


@dataclass
class _CategoryCacheEntry:
    handle: str
    seo_url: Optional[str]
    parent_handle: Optional[str]
    fetched_at: float


_CATEGORY_CACHE: Dict[str, _CategoryCacheEntry] = {}
_CATEGORY_CACHE_TTL = 3600.0  # seconds
_CATEGORY_CACHE_LOCK = threading.Lock()


def _normalize_category_path(value: str) -> str:
    parts = [segment.strip("/") for segment in value.split("/") if segment.strip("/")]
    return "/".join(parts)


def _extract_text_value(raw: Any) -> Optional[str]:
    if isinstance(raw, str):
        cleaned = raw.strip()
        return cleaned or None
    if isinstance(raw, dict):
        for key in ("en", "lv", "ru", "lt", "et", "de", "fr", "es"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in raw.values():
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes, dict)):
        for item in raw:
            candidate = _extract_text_value(item)
            if candidate:
                return candidate
    return None


def fetch_category(handle: str, timeout: int = 10) -> Tuple[bool, Dict[str, Any]]:
    """Fetch Mozello category by handle."""
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}
    target = (handle or "").strip()
    if not target:
        return False, {"error": "handle_required"}
    try:
        _throttle_wait()
        r = requests.get(_api_url(f"/store/category/{target}/"), headers=headers, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code == 404:
            return False, {"error": "not_found"}
        if r.status_code != 200 or data.get("error") is True:
            return False, {"error": "http_error", "status": r.status_code, "details": data}
        return True, data
    except Exception as exc:  # pragma: no cover - defensive network handling
        LOG.warning("fetch_category failed handle=%s error=%s", handle, exc)
        return False, {"error": str(exc)}


def _category_cache_lookup(handle: str, *, force_refresh: bool = False) -> Optional[_CategoryCacheEntry]:
    key = (handle or "").strip()
    if not key:
        return None
    now = time.time()
    with _CATEGORY_CACHE_LOCK:
        entry = _CATEGORY_CACHE.get(key)
        if entry and not force_refresh and now - entry.fetched_at < _CATEGORY_CACHE_TTL:
            return entry
    ok, payload = fetch_category(key)
    if not ok:
        # Only log at debug level to avoid noise when resolving legacy categories.
        LOG.debug("category lookup failed handle=%s details=%s", key, payload)
        with _CATEGORY_CACHE_LOCK:
            stale = _CATEGORY_CACHE.get(key)
        return stale
    data = payload.get("category") if isinstance(payload.get("category"), dict) else payload
    if not isinstance(data, dict):
        return None
    seo_field = data.get("seo_url") or data.get("seoUrl")
    seo_url = _extract_text_value(seo_field)
    if not seo_url:
        path_field = data.get("path")
        if isinstance(path_field, Iterable):
            segments: List[str] = []
            for entry in path_field:
                segment = _extract_text_value(entry)
                if segment:
                    segments.append(_normalize_category_path(segment))
            if segments:
                seo_url = "/".join(part for part in segments if part)
    parent_field = data.get("parent_handle")
    parent_handle = parent_field.strip() if isinstance(parent_field, str) and parent_field.strip() else None
    entry = _CategoryCacheEntry(handle=key, seo_url=seo_url, parent_handle=parent_handle, fetched_at=time.time())
    with _CATEGORY_CACHE_LOCK:
        _CATEGORY_CACHE[key] = entry
    return entry


def resolve_category_url_path(category_handle: Optional[str], *, force_refresh: bool = False) -> Optional[str]:
    """Return seo_url path for category and its parents (e.g. 'parent/child')."""
    raw = (category_handle or "").strip()
    if not raw:
        return None
    if "/" in raw:
        return _normalize_category_path(raw)
    segments: List[str] = []
    visited: Set[str] = set()
    current = raw
    refresh_flag = force_refresh
    while current and current not in visited:
        visited.add(current)
        entry = _category_cache_lookup(current, force_refresh=refresh_flag)
        refresh_flag = False
        if not entry:
            break
        slug_source = entry.seo_url or entry.handle
        normalized = _normalize_category_path(slug_source)
        if normalized:
            segments.append(normalized)
        current = (entry.parent_handle or "").strip()
    if not segments:
        return None
    segments.reverse()
    return "/".join(segments)


def extract_product_slug(product_payload: Dict[str, Any]) -> Optional[str]:
    if not isinstance(product_payload, dict):
        return None
    product = product_payload.get("product") if isinstance(product_payload.get("product"), dict) else product_payload
    if not isinstance(product, dict):
        return None
    url_field = product.get("url")
    candidate: Optional[str] = None
    if isinstance(url_field, dict):
        value = url_field.get("en")
        candidate = value if isinstance(value, str) else None
    elif isinstance(url_field, str):
        candidate = url_field
    if not candidate and isinstance(product.get("handle"), str):
        candidate = product.get("handle")
    if not candidate:
        return None
    cleaned = candidate.strip().strip("/")
    return cleaned or None


def build_relative_product_path(
    handle: Optional[str],
    category_handle: Optional[str],
    product_slug: Optional[str],
    *,
    force_refresh: bool = False,
) -> Optional[str]:
    handle_clean = (handle or "").strip()
    if not handle_clean:
        return None
    slug = (product_slug or "").strip().strip("/")
    category_path = resolve_category_url_path(category_handle, force_refresh=force_refresh) if category_handle else None
    category_parts: List[str] = []
    if category_path:
        category_parts = [part for part in category_path.split("/") if part]

    slug_parts: List[str] = []
    if slug:
        slug_parts = [part for part in slug.split("/") if part]
    else:
        slug_parts = [handle_clean.strip("/")]

    if category_parts and slug_parts[:len(category_parts)] == category_parts:
        combined_parts = slug_parts
    else:
        combined_parts = category_parts + slug_parts

    if not combined_parts:
        combined_parts = [handle_clean.strip("/")]

    relative = "/".join(["store", "item", *combined_parts])
    return f"/{relative.strip('/')}/"


def _normalize_full_url_value(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    return cleaned if cleaned.startswith("/") else f"/{cleaned.lstrip('/')}"


def _resolve_full_url_from_field(full_url_field: Any, preferred_language: Optional[str]) -> Optional[str]:
    if full_url_field is None:
        return None
    if isinstance(full_url_field, dict):
        priority: List[str] = []
        if preferred_language:
            priority.append(preferred_language)
        # try a few known store languages before falling back to whatever Mozello sent
        priority.extend(["en", "lv", "ru", "de", "fr", "es", "lt", "et"])
        seen: Set[str] = set()
        ordered: List[str] = []
        for code in priority:
            if code and code not in seen:
                ordered.append(code)
                seen.add(code)
        for code in ordered:
            normalized = _normalize_full_url_value(full_url_field.get(code))  # type: ignore[arg-type]
            if normalized:
                return normalized
        for value in full_url_field.values():
            normalized = _normalize_full_url_value(value)
            if normalized:
                return normalized
        return None
    return _normalize_full_url_value(full_url_field)


def derive_relative_url_from_product(
    product_payload: Dict[str, Any],
    preferred_language: Optional[str] = None,
    *,
    force_refresh: bool = False,
) -> Optional[str]:
    if not isinstance(product_payload, dict):
        return None
    product = product_payload.get("product") if isinstance(product_payload.get("product"), dict) else product_payload
    if not isinstance(product, dict):
        return None
    normalized_pref: Optional[str] = None
    if isinstance(preferred_language, str):
        cleaned_pref = preferred_language.strip()
        if cleaned_pref:
            normalized_pref = _normalize_product_language(cleaned_pref)
    full_url_field = product.get("full_url") or product.get("fullUrl")
    from_full = _resolve_full_url_from_field(full_url_field, normalized_pref)
    if from_full:
        return from_full
    handle = product.get("handle")
    category_handle = product.get("category_handle") if isinstance(product.get("category_handle"), str) else None
    slug = extract_product_slug(product)
    return build_relative_product_path(handle, category_handle, slug, force_refresh=force_refresh)


def _normalize_product_language(code: Optional[str]) -> str:
    mapping = {
        "en": "en",
        "eng": "en",
        "lv": "lv",
        "lav": "lv",
        "lvs": "lv",
        "ru": "ru",
        "rus": "ru",
    }
    if not code:
        return "en"
    normalized = code.strip().lower()
    if not normalized:
        return "en"
    return mapping.get(normalized, "en")


def _resolve_api_key() -> Optional[str]:
    cfg = _get_singleton(create=False)
    if cfg and cfg.api_key:
        cleaned = cfg.api_key.strip()
        if cleaned:
            return cleaned
    env_key = config.mozello_api_key()
    if env_key:
        cleaned_env = env_key.strip()
        if cleaned_env:
            if not cfg or not (cfg.api_key and cfg.api_key.strip()):
                try:
                    update_settings(cleaned_env, None, None)
                    LOG.info("Mozello API key seeded from environment into mozello_config table.")
                except Exception:  # pragma: no cover - best effort
                    LOG.warning("Failed persisting Mozello API key from environment", exc_info=True)
            return cleaned_env
    return None


def _seed_store_url_from_env() -> None:
    env_url = config.mozello_store_url()
    if not env_url:
        return
    cleaned_env = env_url.strip()
    if not cleaned_env:
        return
    try:
        _ensure_schema_migrations()
        with app_session() as s:
            cfg = s.get(MozelloConfig, 1)
            if cfg is None:
                cfg = MozelloConfig(id=1)
                s.add(cfg)
            existing = (cfg.store_url or "").strip()
            if not existing:
                cfg.store_url = cleaned_env
                LOG.info("Mozello store URL seeded from environment into mozello_config table.")
    except Exception:  # pragma: no cover - defensive
        LOG.warning("Failed seeding Mozello store URL from environment", exc_info=True)


def _current_store_url() -> Optional[str]:
    cfg = _get_singleton(create=False)
    if cfg and cfg.store_url:
        cleaned = cfg.store_url.strip()
        return cleaned or None
    return None


def get_store_url() -> Optional[str]:
    """Return configured Mozello store base URL if available."""
    _seed_store_url_from_env()
    value = _current_store_url()
    if value:
        return value.rstrip("/")
    env_value = config.mozello_store_url()
    if env_value:
        cleaned_env = env_value.strip()
        return cleaned_env.rstrip("/") if cleaned_env else None
    return None
def get_app_settings() -> Dict[str, Any]:
    seeded_key = _resolve_api_key()
    _seed_store_url_from_env()
    cfg = _get_singleton(create=True)
    key_value = cfg.api_key.strip() if cfg and isinstance(cfg.api_key, str) else None
    if not key_value and seeded_key:
        key_value = seeded_key.strip() or None
    url_value = cfg.store_url.strip() if cfg and isinstance(cfg.store_url, str) else None
    if not url_value:
        env_url = config.mozello_store_url()
        if env_url:
            url_value = env_url.strip() or None
    return {
        "mz_store_url": url_value or None,
        "mz_api_key": key_value or None,
        "mz_api_key_set": bool(key_value),
    }


def update_app_settings(store_url: Optional[str], api_key: Optional[str]) -> Dict[str, Any]:
    _ensure_schema_migrations()
    with app_session() as s:
        cfg = s.get(MozelloConfig, 1)
        if cfg is None:
            cfg = MozelloConfig(id=1)
            s.add(cfg)
        changed = False

        if store_url is not None:
            sanitized_url = (store_url or "").strip() or None
            if cfg.store_url != sanitized_url:
                cfg.store_url = sanitized_url
                changed = True

        if api_key is not None:
            sanitized_key = (api_key or "").strip() or None
            if cfg.api_key != sanitized_key:
                cfg.api_key = sanitized_key
                changed = True

        if changed:
            LOG.info(
                "Mozello app settings updated store_url_set=%s api_key_set=%s",
                bool(cfg.store_url),
                bool(cfg.api_key),
            )

    return get_app_settings()


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


def update_settings(api_key: Optional[str], notifications_url: Optional[str], events: Optional[List[str]]) -> Dict[str, Any]:
    sanitized_key: Optional[str] = None
    with app_session() as s:
        cfg = s.get(MozelloConfig, 1)
        if cfg is None:
            cfg = MozelloConfig(id=1)
            s.add(cfg)
        if api_key is not None:
            sanitized_key = (api_key or "").strip() or None
            cfg.api_key = sanitized_key
        # notifications_url now computed dynamically; ignore writes unless explicitly provided (migration support)
        if notifications_url:
            cfg.notifications_url = notifications_url.strip() or None
        if events is not None:
            cfg.set_events(events)
        LOG.info(
            "Mozello settings updated url=%s events=%s api_key_set=%s",
            cfg.notifications_url,
            cfg.events_list(),
            bool(sanitized_key or cfg.api_key),
        )

    return get_settings()


def allowed_events() -> List[str]:
    return list(MozelloConfig.ALLOWED_EVENTS)


def verify_signature(raw_body: bytes, provided_hash: str, api_key: str) -> bool:
    expected = base64.b64encode(hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode()
    try:
        return hmac.compare_digest(expected, provided_hash or "")
    except Exception:
        return False


def handle_webhook(raw_body: bytes, headers: Dict[str, str]) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Verify and parse inbound Mozello webhook payload.

    Returns (accepted, event, payload). Payload is None when rejected.
    """
    api_key = _resolve_api_key()
    if not api_key:
        return False, "api_key_not_configured", None
    provided = headers.get("X-Mozello-Hash") or headers.get("x-mozello-hash", "")
    # Allow explicit local test bypass (not sent by Mozello) only if header present
    if headers.get("X-Mozello-Test", "").lower() == "unsigned" and provided == "":
        pass
    else:
        if not verify_signature(raw_body, provided, api_key):
            return False, "signature_invalid", None
    # Parse JSON (defensive)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False, "invalid_json", None
    evt_raw = payload.get("event")
    evt = str(evt_raw).strip().upper() if evt_raw else ""
    order_info = payload.get("order") if isinstance(payload.get("order"), dict) else None
    order_id = order_info.get("order_id") if isinstance(order_info, dict) else None
    LOG.info("Mozello webhook accepted event=%s order=%s", evt or "UNKNOWN", order_id)
    return True, evt or "UNKNOWN", payload

__all__ = [
    "get_settings",
    "update_settings",
    "allowed_events",
    "handle_webhook",
    "get_app_settings",
    "get_store_url",
    "update_app_settings",
    "fetch_category",
    "resolve_category_url_path",
    "extract_product_slug",
    "build_relative_product_path",
    "derive_relative_url_from_product",
]


def _get_api_key_raw() -> Optional[str]:
    try:
        cfg = _get_singleton(create=True)
        if cfg and cfg.api_key:
            cleaned = cfg.api_key.strip()
            return cleaned or None
        return None
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
            if "store_url" not in cols:
                LOG.info("Applying schema migration: adding mozello_config.store_url column")
                s.execute(text("ALTER TABLE mozello_config ADD COLUMN store_url VARCHAR(500)"))
    except Exception as exc:
        LOG.error("Mozello schema migration check failed: %s", exc)
    finally:
        _SCHEMA_CHECKED = True

__all__.append("_ensure_schema_migrations")


# --------------------- Outbound Mozello Sync ---------------------------

def _api_headers() -> Dict[str, str]:
    key = _resolve_api_key() or ""
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

# --------------------- Product Catalog Helpers (throttled) --------------

_THROTTLE_LOCK = threading.Lock()
_LAST_API_CALL = 0.0
_MIN_INTERVAL = 1.0  # seconds between ANY Mozello API call (rule #18)


def _throttle_wait():  # pragma: no cover (timing)
    global _LAST_API_CALL
    with _THROTTLE_LOCK:
        now = time.time()
        delta = now - _LAST_API_CALL
        if delta < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - delta)
        _LAST_API_CALL = time.time()


def _api_url(path: str) -> str:
    base = config.mozello_api_base().rstrip('/')
    if not path.startswith('/'):
        path = '/' + path
    return base + path


def list_products_full(page_size: int = 100, max_pages: int = 200) -> Tuple[bool, Dict[str, Any]]:
    """Fetch all products (paginated). Returns (ok, data).

    data keys on success: { products: [...], count: int }
    On error: { error: str, details? }
    """
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}
    products: List[Dict[str, Any]] = []
    next_url = _api_url(f"/store/products/?page_size={int(page_size)}")
    pages = 0
    try:
        while next_url and pages < max_pages:
            _throttle_wait()
            r = requests.get(next_url, headers=headers, timeout=15)
            pages += 1
            status = r.status_code
            try:
                payload = r.json()
            except Exception:
                return False, {"error": "invalid_json", "status": status}
            if status != 200 or payload.get("error") is True:
                return False, {"error": "http_error", "status": status, "details": payload}
            page_items = payload.get("products") or []
            for p in page_items:
                relative_url = derive_relative_url_from_product(p)
                products.append({
                    "handle": p.get("handle"),
                    "title": (p.get("title") if isinstance(p.get("title"), str) else (p.get("title", {}).get("en") if isinstance(p.get("title"), dict) else None)),
                    "price": p.get("price"),
                    "category_handle": p.get("category_handle") if isinstance(p.get("category_handle"), str) else None,
                    "relative_url": relative_url,
                })
            next_rel = payload.get("next_page_uri")
            if next_rel:
                base = config.mozello_api_base().rstrip('/')
                next_url = base + next_rel
            else:
                next_url = None
        return True, {"products": products, "count": len(products), "pages": pages}
    except Exception as exc:  # pragma: no cover
        LOG.warning("list_products_full failed: %s", exc)
        return False, {"error": str(exc)}


def fetch_product(handle: str, timeout: int = 10) -> Tuple[bool, Dict[str, Any]]:
    """Fetch a single Mozello product by handle."""
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}
    target = (handle or "").strip()
    if not target:
        return False, {"error": "handle_required"}
    try:
        _throttle_wait()
        r = requests.get(_api_url(f"/store/product/{target}/"), headers=headers, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code == 404:
            return False, {"error": "not_found"}
        if r.status_code != 200 or data.get("error") is True:
            return False, {"error": "http_error", "status": r.status_code, "details": data}
        return True, data
    except Exception as exc:  # pragma: no cover
        LOG.warning("fetch_product failed handle=%s error=%s", handle, exc)
        return False, {"error": str(exc)}


def upsert_product_minimal(handle: str, title: str, price: float | None) -> Tuple[bool, Dict[str, Any]]:
    """Create or update a single product with minimal fields.

    Strategy: attempt PUT (update). If 404, attempt POST (create).
    """
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}
    body = {"product": {"title": {"en": title}, "price": price or 0.0, "visible": True}}
    # Update first
    try:
        _throttle_wait()
        r = requests.put(_api_url(f"/store/product/{handle}/"), json=body, headers=headers, timeout=15)
        if r.status_code == 404:
            # Create
            create_body = {"product": {"handle": handle, "title": {"en": title}, "price": price or 0.0, "visible": True}}
            _throttle_wait()
            r = requests.post(_api_url("/store/product/"), json=create_body, headers=headers, timeout=15)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code != 200 or data.get("error") is True:
            return False, {"error": "http_error", "status": r.status_code, "details": data}
        return True, data
    except Exception as exc:  # pragma: no cover
        return False, {"error": str(exc)}


def upsert_product_basic(
    handle: str,
    title: str,
    price: float | None,
    description_html: Optional[str],
    language_code: Optional[str],
) -> Tuple[bool, Dict[str, Any]]:
    """Create or update product including optional description.

    If description_html provided it maps to Mozello `description` (multilanguage single-language shortcut).
    Fallback to create when update indicates the product is missing.
    """
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}

    clean_handle = (handle or "").strip()
    if not clean_handle:
        return False, {"error": "handle_required"}

    title_clean = (title or "").strip()
    if not title_clean:
        return False, {"error": "title_required"}

    selected_language = _normalize_product_language(language_code)

    price_value = 0.0
    if price is not None:
        try:
            price_value = float(price)
        except Exception:
            price_value = 0.0

    product_obj: Dict[str, Any] = {
        "title": {selected_language: title_clean},
        "price": price_value,
        "visible": True,
        # Keep Mozello product URL aligned with Calibre/Mozello handle.
        "url": {selected_language: clean_handle},
    }
    description_clean = (description_html or "").strip()
    if description_clean:
        product_obj["description"] = {selected_language: description_clean}

    update_payload: Dict[str, Any] = {"product": product_obj}
    create_payload: Optional[Dict[str, Any]] = None

    def _parse_response(resp: requests.Response) -> Dict[str, Any]:
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    update_status: Optional[int] = None
    update_details: Optional[Dict[str, Any]] = None

    try:
        _throttle_wait()
        update_resp = requests.put(
            _api_url(f"/store/product/{clean_handle}/"),
            json=update_payload,
            headers=headers,
            timeout=20,
        )
        update_status = update_resp.status_code
        update_details = _parse_response(update_resp)
        if update_status == 200 and not (isinstance(update_details, dict) and update_details.get("error") is True):
            return True, update_details or {}
        LOG.warning(
            "Mozello product update failed handle=%s status=%s lang=%s body=%s payload=%s",
            clean_handle,
            update_status,
            selected_language,
            update_details,
            update_payload,
        )
    except Exception as exc:  # pragma: no cover - network defensive
        LOG.error("Mozello product update exception handle=%s error=%s", clean_handle, exc)
        return False, {"error": str(exc), "update_request": update_payload, "language": selected_language}

    if update_status in (401, 403):
        return False, {
            "error": "http_error",
            "status": update_status,
            "details": update_details,
            "update_request": update_payload,
            "update_status": update_status,
            "update_details": update_details,
            "language": selected_language,
        }

    should_create = False
    if update_status == 404:
        should_create = True
    else:
        fetch_ok, fetch_payload = fetch_product(clean_handle)
        if not fetch_ok and fetch_payload.get("error") == "not_found":
            should_create = True
        else:
            if not fetch_ok:
                LOG.warning(
                    "Mozello product fetch after update failure handle=%s error=%s",
                    clean_handle,
                    fetch_payload,
                )
            error_payload: Dict[str, Any] = {
                "error": "http_error",
                "status": update_status,
                "details": update_details,
                "update_request": update_payload,
                "update_status": update_status,
                "update_details": update_details,
                "language": selected_language,
            }
            if not fetch_ok:
                error_payload["fetch_error"] = fetch_payload
            return False, error_payload

    create_body = {"product": {"handle": clean_handle, **product_obj}}
    create_payload = create_body
    try:
        _throttle_wait()
        create_resp = requests.post(
            _api_url("/store/product/"),
            json=create_body,
            headers=headers,
            timeout=20,
        )
        create_status = create_resp.status_code
        create_details = _parse_response(create_resp)
        if create_status != 200 or (isinstance(create_details, dict) and create_details.get("error") is True):
            LOG.error(
                "Mozello product create failed handle=%s status=%s lang=%s body=%s update_status=%s payload=%s",
                clean_handle,
                create_status,
                selected_language,
                create_details,
                update_status,
                create_payload,
            )
            return False, {
                "error": "http_error",
                "status": create_status,
                "details": create_details,
                "update_status": update_status,
                "update_details": update_details,
                "update_request": update_payload,
                "create_request": create_payload,
                "create_details": create_details,
                "language": selected_language,
            }
        return True, create_details
    except Exception as exc:  # pragma: no cover - network defensive
        LOG.error("Mozello product create exception handle=%s error=%s", clean_handle, exc)
        error_payload: Dict[str, Any] = {
            "error": str(exc),
            "context": "create_attempt",
            "update_request": update_payload,
            "language": selected_language,
        }
        if create_payload is not None:
            error_payload["create_request"] = create_payload
        return False, error_payload

__all__.append("upsert_product_basic")


def update_product_price(handle: str, price: float | None) -> Tuple[bool, Dict[str, Any]]:
    """Update only the price for an existing Mozello product.

    Keeps title/description untouched to avoid overwriting store content. Does not create products.
    """
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}
    clean_handle = (handle or "").strip()
    if not clean_handle:
        return False, {"error": "handle_required"}
    price_value = 0.0
    if price is not None:
        try:
            price_value = float(price)
        except Exception:
            price_value = 0.0
    payload = {"product": {"price": price_value}}
    try:
        _throttle_wait()
        resp = requests.put(_api_url(f"/store/product/{clean_handle}/"), json=payload, headers=headers, timeout=15)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        if resp.status_code != 200 or data.get("error") is True:
            return False, {"error": "http_error", "status": resp.status_code, "details": data}
        return True, data
    except Exception as exc:  # pragma: no cover - network defensive
        LOG.warning("update_product_price failed handle=%s: %s", clean_handle, exc)
        return False, {"error": str(exc)}

__all__.append("update_product_price")


def delete_product(handle: str) -> Tuple[bool, Dict[str, Any]]:
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}
    try:
        _throttle_wait()
        r = requests.delete(_api_url(f"/store/product/{handle}/"), headers=headers, timeout=15)
        if r.status_code == 404:
            return True, {"status": "not_found"}
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code != 200 or data.get("error") is True:
            return False, {"error": "http_error", "status": r.status_code, "details": data}
        return True, {"status": "deleted"}
    except Exception as exc:  # pragma: no cover
        return False, {"error": str(exc)}

__all__.extend(["list_products_full", "fetch_product", "upsert_product_minimal", "delete_product"])


def fetch_paid_orders(
    page_size: int = 100,
    max_pages: int = 50,
    *,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> Tuple[bool, Dict[str, Any]]:
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}
    query_parts = ["desc=1", f"page_size={int(page_size)}"]
    filters: List[str] = []
    if start_date:
        filters.append(f"created_at>={start_date.strftime('%Y-%m-%d %H:%M:%S')}")
    if end_date:
        filters.append(f"created_at<={end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    for expr in filters:
        query_parts.append(f"filter={quote_plus(expr)}")
    query_str = "&".join(query_parts)
    next_url = _api_url(f"/store/orders/?{query_str}")
    orders: List[Dict[str, Any]] = []
    pages = 0
    try:
        while next_url and pages < max_pages:
            _throttle_wait()
            r = requests.get(next_url, headers=headers, timeout=20)
            pages += 1
            status = r.status_code
            try:
                payload = r.json()
            except Exception:
                return False, {"error": "invalid_json", "status": status}
            if status != 200 or payload.get("error") is True:
                return False, {"error": "http_error", "status": status, "details": payload}
            batch = payload.get("orders") or []
            if isinstance(batch, list):
                for entry in batch:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("payment_status") != "paid":
                        continue
                    if entry.get("archived") is True:
                        continue
                    orders.append(entry)
            next_rel = payload.get("next_page_uri")
            if next_rel:
                base = config.mozello_api_base().rstrip('/')
                next_url = base + next_rel
            else:
                next_url = None
        return True, {"orders": orders, "count": len(orders), "pages": pages}
    except Exception as exc:  # pragma: no cover - network defensive
        LOG.warning("fetch_paid_orders failed: %s", exc)
        return False, {"error": str(exc)}


__all__.append("fetch_paid_orders")


# --------------------- Product Pictures --------------------------------------

def add_product_picture(handle: str, b64_image: str, filename: str | None = None) -> Tuple[bool, Dict[str, Any]]:
    """Upload a picture for a product.

    Assumptions (per internal doc mozello_store_api.md §6 table Product Pictures):
      POST /store/product/<handle>/picture/ accepts JSON body with base64 data field.
    Using body shape { "picture": { "data": <base64> } } (adjust if spec differs).
    """
    headers = _api_headers()
    if not headers:
        return False, {"error": "api_key_missing"}
    picture_obj: Dict[str, Any] = {"data": b64_image}
    if filename:
        picture_obj["filename"] = filename
    body = {"picture": picture_obj}
    try:
        _throttle_wait()
        r = requests.post(_api_url(f"/store/product/{handle}/picture/"), json=body, headers=headers, timeout=30)
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}
        if r.status_code != 200 or data.get("error") is True:
            return False, {"error": "http_error", "status": r.status_code, "details": data}
        return True, data
    except Exception as exc:  # pragma: no cover
        return False, {"error": str(exc)}

__all__.append("add_product_picture")
