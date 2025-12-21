#!/usr/bin/env python3
"""Minimal Mozello Store API mock for local QA.

Implements only the endpoints required by ebooks_lv Mozello integration:
- GET /v1/store/product/<handle>/
- PUT /v1/store/product/<handle>/
- POST /v1/store/product/
- GET /v1/store/product/<handle>/pictures/
- POST /v1/store/product/<handle>/picture/
- DELETE /v1/store/product/<handle>/picture/<uid>/
- GET /v1/store/products/ (basic empty list)

This is intentionally tiny and dependency-free (stdlib only).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length else b""
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _auth_ok(handler: BaseHTTPRequestHandler) -> bool:
    # ebooks_lv sends: Authorization: ApiKey <key>
    auth = handler.headers.get("Authorization") or ""
    return auth.startswith("ApiKey ")


def _merge_text(existing, incoming):
    # Multilanguage text merge: keep existing language keys unless overwritten.
    if isinstance(existing, dict) and isinstance(incoming, dict):
        out = dict(existing)
        out.update(incoming)
        return out
    return incoming


class _State:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.products: dict[str, dict] = {}
        self.pictures: dict[str, list[dict]] = {}


STATE = _State()


class Handler(BaseHTTPRequestHandler):
    server_version = "mozello-mock/0.1"

    def log_message(self, fmt: str, *args):
        # Keep QA output quieter.
        if os.getenv("MZ_MOCK_VERBOSE") == "1":
            super().log_message(fmt, *args)

    def do_GET(self):
        if not _auth_ok(self):
            return _json_response(self, 401, {"error": True, "error_code": "unauthorized"})

        parsed = urlparse(self.path)
        path = parsed.path

        # GET /v1/store/products/
        if re.fullmatch(r"/v1/store/products/", path):
            qs = parse_qs(parsed.query or "")
            page_size = int((qs.get("page_size") or ["100"])[0])
            with STATE.lock:
                handles = sorted(STATE.products.keys())
                items = []
                for h in handles[:page_size]:
                    p = STATE.products[h]
                    items.append({
                        "handle": h,
                        "title": p.get("title"),
                        "price": p.get("price"),
                        "category_handle": p.get("category_handle"),
                        "url": p.get("url"),
                        "full_url": p.get("full_url"),
                    })
            return _json_response(self, 200, {"error": False, "products": items, "next_page_uri": None})

        # GET /v1/store/product/<handle>/
        m = re.fullmatch(r"/v1/store/product/([^/]+)/", path)
        if m:
            handle = m.group(1)
            with STATE.lock:
                product = STATE.products.get(handle)
                pics = STATE.pictures.get(handle, [])
            if not product:
                return _json_response(self, 404, {"error": True, "error_code": "not_found"})
            payload = dict(product)
            payload["handle"] = handle
            payload["pictures"] = [{"uid": p["uid"], "url": p["url"]} for p in pics]
            return _json_response(self, 200, {"error": False, "product": payload})

        # GET /v1/store/product/<handle>/pictures/
        m = re.fullmatch(r"/v1/store/product/([^/]+)/pictures/", path)
        if m:
            handle = m.group(1)
            with STATE.lock:
                pics = list(STATE.pictures.get(handle, []))
            return _json_response(self, 200, {"error": False, "pictures": [{"uid": p["uid"], "url": p["url"]} for p in pics]})

        return _json_response(self, 404, {"error": True, "error_code": "not_found"})

    def do_POST(self):
        if not _auth_ok(self):
            return _json_response(self, 401, {"error": True, "error_code": "unauthorized"})

        parsed = urlparse(self.path)
        path = parsed.path
        body = _read_json(self)

        # POST /v1/store/product/
        if re.fullmatch(r"/v1/store/product/", path):
            product = body.get("product") if isinstance(body, dict) else None
            if not isinstance(product, dict):
                return _json_response(self, 400, {"error": True, "error_code": "invalid_payload"})
            handle = (product.get("handle") or "").strip()
            if not handle:
                return _json_response(self, 400, {"error": True, "error_code": "handle_required"})
            with STATE.lock:
                STATE.products.setdefault(handle, {})
                STATE.products[handle].update({k: v for k, v in product.items() if k != "handle"})
                STATE.pictures.setdefault(handle, [])
            return _json_response(self, 200, {"error": False, "product": {"handle": handle}})

        # POST /v1/store/product/<handle>/picture/
        m = re.fullmatch(r"/v1/store/product/([^/]+)/picture/", path)
        if m:
            handle = m.group(1)
            picture = body.get("picture") if isinstance(body, dict) else None
            if not isinstance(picture, dict):
                return _json_response(self, 400, {"error": True, "error_code": "invalid_payload"})
            uid = f"uid-{int(time.time() * 1000)}"
            url = f"http://mozello-mock.local/images/{uid}.jpg"
            with STATE.lock:
                STATE.products.setdefault(handle, {})
                STATE.pictures.setdefault(handle, [])
                STATE.pictures[handle].append({"uid": uid, "url": url, "filename": picture.get("filename")})
            return _json_response(self, 200, {"error": False, "picture": {"uid": uid, "url": url}})

        return _json_response(self, 404, {"error": True, "error_code": "not_found"})

    def do_PUT(self):
        if not _auth_ok(self):
            return _json_response(self, 401, {"error": True, "error_code": "unauthorized"})

        parsed = urlparse(self.path)
        path = parsed.path
        body = _read_json(self)

        m = re.fullmatch(r"/v1/store/product/([^/]+)/", path)
        if not m:
            return _json_response(self, 404, {"error": True, "error_code": "not_found"})

        handle = m.group(1)
        product_in = body.get("product") if isinstance(body, dict) else None
        if not isinstance(product_in, dict):
            return _json_response(self, 400, {"error": True, "error_code": "invalid_payload"})

        options = body.get("options") if isinstance(body, dict) else None
        text_merge = isinstance(options, dict) and options.get("text_update_mode") == "merge"

        with STATE.lock:
            if handle not in STATE.products:
                return _json_response(self, 404, {"error": True, "error_code": "not_found"})
            current = STATE.products[handle]

            for k, v in product_in.items():
                if text_merge and k in ("title", "description", "url", "full_url"):
                    current[k] = _merge_text(current.get(k), v)
                else:
                    current[k] = v

        return _json_response(self, 200, {"error": False, "product": {"handle": handle}})

    def do_DELETE(self):
        if not _auth_ok(self):
            return _json_response(self, 401, {"error": True, "error_code": "unauthorized"})

        parsed = urlparse(self.path)
        path = parsed.path

        # DELETE /v1/store/product/<handle>/picture/<uid>/
        m = re.fullmatch(r"/v1/store/product/([^/]+)/picture/([^/]+)/", path)
        if m:
            handle = m.group(1)
            uid = m.group(2)
            with STATE.lock:
                pics = STATE.pictures.get(handle)
                if not pics:
                    return _json_response(self, 404, {"error": True, "error_code": "not_found"})
                before = len(pics)
                STATE.pictures[handle] = [p for p in pics if p.get("uid") != uid]
                after = len(STATE.pictures[handle])
            if before == after:
                return _json_response(self, 404, {"error": True, "error_code": "not_found"})
            return _json_response(self, 200, {"error": False, "status": "deleted"})

        return _json_response(self, 404, {"error": True, "error_code": "not_found"})


def main() -> int:
    host = os.getenv("MZ_MOCK_HOST", "0.0.0.0")
    port = int(os.getenv("MZ_MOCK_PORT", "9090"))
    httpd = HTTPServer((host, port), Handler)
    print(f"[mozello-mock] listening on http://{host}:{port}/v1")
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
