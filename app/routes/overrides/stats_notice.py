"""Injects Calibre-Web attribution notice on the /stats page."""
from __future__ import annotations

from typing import Any, Tuple

from flask import Request, Response, request

from app.utils.logging import get_logger

LOG = get_logger("stats_notice")

NOTICE_MARKER = "stats-submodule-note"
NOTICE_HTML = (
    '<p class="text-muted stats-submodule-note">'
    "<small>This application includes Calibre-web as an unmodified submodule, licensed under GPLv3.</small>"
    "</p>"
)
TARGET_ENDPOINTS = {"about.stats"}
MAX_BODY_SIZE = 2_000_000  # bytes


def _is_target_request(flask_request: Request) -> bool:
    endpoint = flask_request.endpoint or ""
    if endpoint in TARGET_ENDPOINTS:
        return True
    if flask_request.path.rstrip("/") == "/stats":  # fallback if endpoint missing
        return True
    return False


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
    if NOTICE_MARKER.encode("utf-8") in body:
        return True, "already_present"
    return False, "ok"


def _inject_notice(body: bytes) -> bytes:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:  # pragma: no cover
        LOG.debug("stats HTML not utf-8; skipping")
        return body
    anchor = '<table id="stats"'
    anchor_pos = text.find(anchor)
    if anchor_pos == -1:
        return body
    end_tag = "</table>"
    close_pos = text.find(end_tag, anchor_pos)
    if close_pos == -1:
        return body
    insertion = close_pos + len(end_tag)
    updated = text[:insertion] + NOTICE_HTML + text[insertion:]
    return updated.encode("utf-8")


def register_stats_notice(app: Any) -> None:
    if getattr(app, "_stats_notice_hook", False):  # type: ignore[attr-defined]
        return

    @app.after_request  # type: ignore[misc]
    def _stats_notice_after(response: Response):  # type: ignore[override]
        if not _is_target_request(request):
            return response
        skip, reason = _should_skip(response)
        if skip:
            LOG.debug("stats notice skip: %s", reason)
            return response
        body = response.get_data(as_text=False)
        new_body = _inject_notice(body)
        if new_body is not body:
            response.set_data(new_body)
            LOG.debug("stats notice injected")
        return response

    setattr(app, "_stats_notice_hook", True)
    LOG.debug("Stats notice hook registered")


__all__ = ["register_stats_notice"]
