"""Mozello-aligned theme injection.

Injects an additional stylesheet on top of Calibre-Web's Standard Theme without
modifying the upstream /calibre-web sources.

This is implemented as an after_request HTML mutation (similar to other
injections in this repo) so it works regardless of template override mode.
"""

from __future__ import annotations

from typing import Any, Tuple

from flask import Response, url_for

from app.utils.logging import get_logger

LOG = get_logger("mozello_theme_injection")

THEME_INJECT_MARKER = "data-eblv-mozello-theme"
MAX_BODY_SIZE = 1_500_000  # bytes


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
    if THEME_INJECT_MARKER.encode("utf-8") in body:
        return True, "already_present"
    if b"</head>" not in body:
        return True, "head_missing"
    return False, "ok"


def _inject_css(body: bytes) -> bytes:
    try:
        try:
            href = url_for("_app_templates.static", filename="css/mozello_theme.css")
        except Exception:
            href = "/app_static/css/mozello_theme.css"
        tag = f'<link rel="stylesheet" href="{href}" {THEME_INJECT_MARKER}="1">'.encode("utf-8")
        return body.replace(b"</head>", tag + b"</head>", 1)
    except Exception as exc:  # pragma: no cover
        LOG.debug("theme injection failed: %s", exc)
        return body


def register_mozello_theme_injection(app: Any) -> None:
    if getattr(app, "_mozello_theme_injection", False):  # type: ignore[attr-defined]
        return

    @app.after_request  # type: ignore[misc]
    def _after(resp: Response):  # type: ignore[override]
        skip, reason = _should_skip(resp)
        if skip:
            return resp
        body = resp.get_data(as_text=False)
        new_body = _inject_css(body)
        if new_body is not body:
            resp.set_data(new_body)
            LOG.debug("mozello theme injected")
        return resp

    setattr(app, "_mozello_theme_injection", True)
    LOG.debug("mozello theme injection registered")


__all__ = ["register_mozello_theme_injection"]
