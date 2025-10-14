"""Detail page injection utilities (defensive).

Provides a loader wrapper that only mutates templates named detail.html
or basic_detail.html and an after_request fallback that injects the gallery
script into rendered HTML for book detail routes. Modeled after
nav_injection but intentionally conservative to avoid breaking template
inheritance resolution.
"""
from __future__ import annotations

from typing import Any, Tuple
from flask import Response
from jinja2 import BaseLoader, TemplateNotFound

from app.utils.logging import get_logger

LOG = get_logger("detail_injection")

SCRIPT_TAG = '<script src="/app_static/ebookslv_public_gallery.js" defer></script>'
INJECT_MARKER = "ebookslv_public_gallery.js"
MAX_BODY_SIZE = 1_500_000


def _should_skip(response: Response) -> Tuple[bool, str]:
    if response.status_code != 200:
        return True, f"status_{response.status_code}"
    ctype = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in ctype:
        return True, f"ctype_{ctype or 'none'}"
    body = response.get_data(as_text=False)
    if not body:
        return True, "empty_body"
    if len(body) > MAX_BODY_SIZE:
        return True, "body_too_large"
    if INJECT_MARKER.encode("utf-8") in body:
        return True, "already_present"
    return False, "ok"


def _inject_into_body(body: bytes) -> bytes:
    try:
        idx = body.lower().rfind(b"</body>")
        if idx == -1:
            return body
        return body[:idx] + SCRIPT_TAG.encode("utf-8") + b"\n" + body[idx:]
    except Exception as exc:  # pragma: no cover
        LOG.debug("detail injection failed: %s", exc)
        return body


def register_response_injection(app: Any) -> None:
    if getattr(app, "_ebookslv_detail_inject_after", False):  # type: ignore[attr-defined]
        return

    @app.after_request
    def _detail_after(resp: Response):
        try:
            from flask import request as _req
            path = getattr(_req, "path", "")
            if not (path.startswith("/book/") or path.startswith("/basic_book/")):
                return resp
            skip, reason = _should_skip(resp)
            if skip:
                LOG.debug("detail after_request skip: %s", reason)
                return resp
            body = resp.get_data(as_text=False)
            new_body = _inject_into_body(body)
            if new_body is not body:
                resp.set_data(new_body)
                LOG.debug("detail injected (after mode)")
        except Exception as exc:  # pragma: no cover
            LOG.debug("detail after_request failed: %s", exc)
        return resp

    setattr(app, "_ebookslv_detail_inject_after", True)
    LOG.debug("detail response injection registered")


class _DetailPatchedLoader(BaseLoader):
    def __init__(self, wrapped: BaseLoader):  # type: ignore[override]
        self._wrapped = wrapped

    def get_source(self, environment, template):  # type: ignore[override]
        try:
            source, filename, uptodate = self._wrapped.get_source(environment, template)  # type: ignore[attr-defined]
        except TemplateNotFound:
            raise
        # If our script is already present, skip
        if INJECT_MARKER in source:
            return source, filename, uptodate
        try:
            tname = template.split('/')[-1]
            # Only mutate well-known detail templates
            if not (tname == 'detail.html' or tname.endswith('detail.html') or tname == 'basic_detail.html'):
                return source, filename, uptodate
            pos = source.lower().rfind("</body>")
            if pos == -1:
                return source, filename, uptodate
            new_source = source[:pos] + SCRIPT_TAG + "\n" + source[pos:]
            LOG.debug("detail injected (loader) template=%s", template)
            return new_source, filename, uptodate
        except Exception as exc:  # pragma: no cover
            LOG.debug("detail loader injection failed: %s", exc)
            return source, filename, uptodate


def register_loader_injection(app: Any) -> None:
    if getattr(app, "_ebookslv_detail_loader", False):  # type: ignore[attr-defined]
        return
    env = getattr(app, "jinja_env", None)
    if not env or not getattr(env, "loader", None):
        return
    # Avoid adding another wrapper if nav_injection already wrapped the loader
    try:
        from app.routes.overrides import nav_injection
        if isinstance(env.loader, nav_injection._NavPatchedLoader) or (
            hasattr(env.loader, '_wrapped') and isinstance(env.loader._wrapped, nav_injection._NavPatchedLoader)
        ):
            setattr(app, "_ebookslv_detail_loader", True)
            LOG.debug("detail loader wrapper skipped because nav_injection is present")
            return
    except Exception:
        pass
    if isinstance(env.loader, _DetailPatchedLoader):
        return
    env.loader = _DetailPatchedLoader(env.loader)  # type: ignore[assignment]
    setattr(app, "_ebookslv_detail_loader", True)
    LOG.debug("detail loader wrapper registered")


__all__ = ["register_response_injection", "register_loader_injection"]
