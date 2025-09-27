"""Navigation link injection utilities.

Working (proven) strategy kept: BOTH a template-loader pre-render patch and an
after_request HTML mutation fallback. This version restores the previously
stable dual-function API after a simplification attempt caused the link to
disappear again in your environment.

Exports:
    register_loader_injection(app)
    register_response_injection(app)

Call both during init for maximum robustness. No environment variables control
this feature (always on). Safe if called multiple times.
"""

from __future__ import annotations

from typing import Any, Tuple
from flask import Response
from jinja2 import BaseLoader, TemplateNotFound

from .logging_setup import get_logger
from .utils import is_admin_user

LOG = get_logger()

# Constants
PLUGIN_NAV_ID = "top_users_books"
ADMIN_ANCHOR_ID = "top_admin"
INJECT_MARKER = f'id="{PLUGIN_NAV_ID}"'
SEARCH_ANCHOR = f'id="{ADMIN_ANCHOR_ID}"'

LINK_HTML = (
    '<li><a id="top_users_books" data-text="ebooks.lv" '
    'href="/plugin/users_books/admin/ui">'
    '<span class="glyphicon glyphicon-book"></span> '
    '<span class="hidden-sm">ebooks.lv</span></a></li>'
)

LINK_HTML_JINJA = (
    '{% if current_user and current_user.role_admin() %}' + LINK_HTML + '{% endif %}'
)


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
    if INJECT_MARKER.encode("utf-8") in body:
        return True, "already_present"
    if SEARCH_ANCHOR.encode("utf-8") not in body:
        return True, "anchor_missing"
    if not is_admin_user():
        return True, "not_admin"
    return False, "ok"


def _inject_nav_html(body: bytes) -> bytes:
    """Insert link HTML immediately after the admin ``</li>``.

    We search for the first occurrence of the admin anchor id, then the
    subsequent closing </li>. If unsuccessful, return original body.
    """
    try:
        anchor_pos = body.find(SEARCH_ANCHOR.encode("utf-8"))
        if anchor_pos == -1:
            return body
        # Find the closing </li> after anchor
        close_tag = b"</li>"
        close_pos = body.find(close_tag, anchor_pos)
        if close_pos == -1:
            return body
        insertion_point = close_pos + len(close_tag)
        prefix = body[:insertion_point]
        suffix = body[insertion_point:]
        injected = prefix + LINK_HTML.encode("utf-8") + suffix
        return injected
    except Exception as exc:
        LOG.debug("users_books nav injection failed: %s", exc)
        return body


def register_response_injection(app: Any) -> None:
    """Register the after_request handler (idempotent)."""
    if getattr(app, "_users_books_nav_inject_after", False):  # type: ignore[attr-defined]
        return

    @app.after_request  # type: ignore[misc]
    def _users_books_after(resp: Response):  # type: ignore[override]
        skip, reason = _should_skip(resp)
        if skip:
            LOG.debug("users_books nav after_request skip: %s", reason)
            return resp
        body = resp.get_data(as_text=False)
        new_body = _inject_nav_html(body)
        if new_body is not body:
            resp.set_data(new_body)
            LOG.debug("users_books nav injected (after mode)")
        return resp

    setattr(app, "_users_books_nav_inject_after", True)
    LOG.debug("users_books: navigation after_request handler registered")


class _NavPatchedLoader(BaseLoader):
    """Lightweight loader wrapper injecting link into template source once."""

    def __init__(self, wrapped: BaseLoader):  # type: ignore[override]
        self._wrapped = wrapped

    def get_source(self, environment, template):  # type: ignore[override]
        try:
            source, filename, uptodate = self._wrapped.get_source(environment, template)  # type: ignore[attr-defined]
        except TemplateNotFound:
            raise
        if PLUGIN_NAV_ID in source or SEARCH_ANCHOR not in source:
            return source, filename, uptodate
        # Insert unconditional (Jinja-guarded) snippet right after admin </li>
        try:
            anchor_pos = source.find(SEARCH_ANCHOR)
            if anchor_pos == -1:
                return source, filename, uptodate
            close_pos = source.find('</li>', anchor_pos)
            if close_pos == -1:
                return source, filename, uptodate
            insertion_point = close_pos + len('</li>')
            new_source = source[:insertion_point] + LINK_HTML_JINJA + source[insertion_point:]
            LOG.debug("users_books nav injected (loader pre-render) template=%s", template)
            return new_source, filename, uptodate
        except Exception as exc:  # pragma: no cover
            LOG.debug("users_books loader injection failed: %s", exc)
            return source, filename, uptodate


def register_loader_injection(app: Any) -> None:
    if getattr(app, "_users_books_nav_loader", False):  # type: ignore[attr-defined]
        return
    env = getattr(app, "jinja_env", None)
    if not env or not getattr(env, "loader", None):
        return
    if isinstance(env.loader, _NavPatchedLoader):
        return
    env.loader = _NavPatchedLoader(env.loader)  # type: ignore[assignment]
    setattr(app, "_users_books_nav_loader", True)
    LOG.debug("users_books: navigation loader wrapper registered")


__all__ = [
    "register_response_injection",
    "register_loader_injection",
]
