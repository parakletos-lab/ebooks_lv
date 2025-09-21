"""Navigation link injection utilities for users_books plugin.

Purpose:
  Inject a navigation link to the plugin's admin UI ("Users Books") into
  Calibre-Web's header bar for admin users without modifying upstream
  templates (complying with Global Rule 0).

Supported Strategies (select via env `USERS_BOOKS_NAV_INJECT_MODE`):
    1. ``after`` (default): register an ``after_request`` hook and post-process
         the rendered HTML as originally implemented.
    2. ``loader``: wrap Jinja2's template loader to patch the *source* of
         `layout.html` (or any upstream template containing the admin anchor)
         before it is rendered (conceptually similar to a before_render_template
         approach without relying on that specific signal).

The loader mode attempts to modify only the in-memory template source at load
time — it does not write files to disk and respects Global Rule 0.

Safeguards (after mode):
    - Skip if response not HTML/text or status != 200.
    - Skip if body already contains the plugin nav id.
    - Skip if anchor with id ``top_admin`` not found (layout changed / theme).
    - Skip for non-admin users.
    - Skip if body too large (> 1.5 MB) to avoid memory churn.

Disable (optional):
  If an environment variable ``USERS_BOOKS_DISABLE_NAV_INJECT`` is set to a
  truthy value, the injection is disabled (documented but not yet surfaced in
  AGENTS.md since it's internal / low-risk; can be promoted later).

Implementation Notes:
  The string insertion targets the closing ``</li>`` of the admin link list
  element to preserve ordering and styling.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple
import os
from flask import Response
from jinja2 import BaseLoader, TemplateNotFound

from .logging_setup import get_logger
from .utils import is_admin_user

LOG = get_logger()

PLUGIN_NAV_ID = "top_users_books"
ADMIN_ANCHOR_ID = "top_admin"
INJECT_MARKER = f"id=\"{PLUGIN_NAV_ID}\""
SEARCH_ANCHOR = f"id=\"{ADMIN_ANCHOR_ID}\""

LINK_HTML = (
    '<li><a id="top_users_books" data-text="Users Books" '
    'href="/plugin/users_books/admin/ui">'
    '<span class="glyphicon glyphicon-book"></span> '
    '<span class="hidden-sm">Users Books</span></a></li>'
)

# For loader mode we embed a Jinja conditional so the template can be cached
# irrespective of which user (admin or not) first triggers the load.
LINK_HTML_JINJA_CONDITIONAL = (
    '{% if current_user and current_user.role_admin() %}' + LINK_HTML + '{% endif %}'
)

MAX_BODY_SIZE = 1_500_000  # bytes


def _env_truthy(name: str) -> bool:
    val = os.environ.get(name)
    if val is None:
        return False
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _should_skip(response: Response) -> Tuple[bool, str]:
    if _env_truthy("USERS_BOOKS_DISABLE_NAV_INJECT"):
        return True, "disabled_by_env"
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
    """Register the after_request handler (idempotent) (mode=after)."""
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


class _PatchedLoader(BaseLoader):
    """A wrapper loader that patches template sources on load (mode=loader).

    Only intercepts templates containing the admin anchor once; caches the
    patched result so subsequent loads are fast. Does not write to disk.
    """

    def __init__(self, wrapped: BaseLoader):  # type: ignore[override]
        self._wrapped = wrapped
        self._patched_cache = {}

    def get_source(self, environment, template):  # type: ignore[override]
        try:
            source_tuple = self._wrapped.get_source(environment, template)  # type: ignore[attr-defined]
        except TemplateNotFound:  # pragma: no cover - defensive
            raise

        source, filename, uptodate = source_tuple
        # Fast exit if already has link or anchor missing
        if PLUGIN_NAV_ID in source:
            LOG.debug("users_books loader: already contains nav id (template=%s)", template)
            return source_tuple
        if SEARCH_ANCHOR not in source:
            LOG.debug("users_books loader: anchor not found (template=%s)", template)
            return source_tuple
        # Insert after first occurrence of closing </li> following admin anchor
        try:
            anchor_pos = source.find(SEARCH_ANCHOR)
            if anchor_pos == -1:
                return source_tuple
            close_pos = source.find("</li>", anchor_pos)
            if close_pos == -1:
                return source_tuple
            insertion_point = close_pos + len("</li>")
            new_source = source[:insertion_point] + LINK_HTML_JINJA_CONDITIONAL + source[insertion_point:]
            LOG.debug("users_books nav injected (loader mode, jinja conditional) template=%s", template)
            return new_source, filename, uptodate
        except Exception as exc:  # pragma: no cover - defensive
            LOG.debug("users_books loader injection failed: %s", exc)
            return source_tuple


def register_loader_injection(app: Any) -> None:
    """Wrap the Jinja2 loader to support loader-based injection (idempotent)."""
    if getattr(app, "_users_books_nav_inject_loader", False):  # type: ignore[attr-defined]
        return
    env = getattr(app, "jinja_env", None)
    if not env or not getattr(env, "loader", None):
        LOG.debug("users_books loader mode: no environment/loader available")
        return
    # Wrap only once
    original = env.loader
    if isinstance(original, _PatchedLoader):
        return
    env.loader = _PatchedLoader(original)  # type: ignore[assignment]
    setattr(app, "_users_books_nav_inject_loader", True)
    LOG.debug("users_books: navigation loader wrapper registered")


def configure_nav_injection(app: Any) -> None:
    """Decide which injection mode to use based on environment.

    Env: USERS_BOOKS_NAV_INJECT_MODE = 'after' (default) | 'loader' | 'off'
    Also honors USERS_BOOKS_DISABLE_NAV_INJECT as a hard disable.
    """
    if _env_truthy("USERS_BOOKS_DISABLE_NAV_INJECT"):
        LOG.info("users_books nav injection globally disabled by env")
        return
    mode = os.environ.get("USERS_BOOKS_NAV_INJECT_MODE", "after").strip().lower()
    if mode == "off":
        LOG.info("users_books nav injection disabled (mode=off)")
        return
    if mode == "loader":
        register_loader_injection(app)
    else:
        register_response_injection(app)


__all__ = [
    "register_response_injection",
    "register_loader_injection",
    "configure_nav_injection",
]
