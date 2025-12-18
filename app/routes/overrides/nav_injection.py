"""Navigation link injection utilities (app-integrated).

This is an inlined copy of the proven dual-strategy navigation injection
originally shipped inside the legacy users_books plugin. We keep BOTH a
template-loader wrapper (pre-render) and an after_request HTML mutation
fallback to maximize robustness across template caching / override edge
cases.

Public API (idempotent):
    register_loader_injection(app)
    register_response_injection(app)

Always safe to call both during startup. If either path cannot be applied
(e.g., no Jinja environment yet), it simply no-ops.
"""
from __future__ import annotations

from typing import Any, Tuple
from flask import Response
from jinja2 import BaseLoader, TemplateNotFound

try:  # pragma: no cover - Flask-Babel optional in tests
    from flask_babel import gettext as _  # type: ignore
except Exception:  # pragma: no cover
    def _fallback_gettext(message, **kwargs):
        if kwargs:
            try:
                return message % kwargs
            except Exception:
                return message
        return message

    _ = _fallback_gettext  # type: ignore

from app.utils.logging import get_logger
from app.utils.identity import is_admin_user

LOG = get_logger("nav_injection")

PLUGIN_NAV_ID = "top_users_books"
ADMIN_ANCHOR_ID = "top_admin"
INJECT_MARKER = f'id="{PLUGIN_NAV_ID}"'
SEARCH_ANCHOR = f'id="{ADMIN_ANCHOR_ID}"'

def _nav_labels() -> dict[str, str]:
    return {
        "ebooks": _("ebooks.lv"),
    }


def _render_nav_item(element_id: str, href: str, icon: str, label: str) -> str:
    return (
        f'<li><a id="{element_id}" data-text="{label}" '
        f'href="{href}">'
        f'<span class="glyphicon {icon}"></span> '
        f'<span class="hidden-sm">{label}</span></a></li>'
    )


def _render_combined_html() -> str:
    labels = _nav_labels()
    return "".join([
        _render_nav_item("top_users_books", "/admin/ebookslv/", "glyphicon-book", labels["ebooks"]),
    ])


LINK_HTML_JINJA = (
    '{% if current_user and current_user.role_admin() %}'
    '<li><a id="top_users_books" data-text="{{ _("ebooks.lv") }}" href="/admin/ebookslv/">'
    '<span class="glyphicon glyphicon-book"></span> '
    '<span class="hidden-sm">{{ _("ebooks.lv") }}</span></a></li>'
    '{% endif %}'
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
    try:
        anchor_pos = body.find(SEARCH_ANCHOR.encode("utf-8"))
        if anchor_pos == -1:
            return body
        close_tag = b"</li>"
        close_pos = body.find(close_tag, anchor_pos)
        if close_pos == -1:
            return body
        insertion_point = close_pos + len(close_tag)
        combined = _render_combined_html().encode("utf-8")
        return body[:insertion_point] + combined + body[insertion_point:]
    except Exception as exc:  # pragma: no cover
        LOG.debug("nav injection failed: %s", exc)
        return body


def register_response_injection(app: Any) -> None:
    if getattr(app, "_users_books_nav_inject_after", False):  # type: ignore[attr-defined]
        return

    @app.after_request  # type: ignore[misc]
    def _users_books_after(resp: Response):  # type: ignore[override]
        skip, reason = _should_skip(resp)
        if skip:
            LOG.debug("nav after_request skip: %s", reason)
            return resp
        body = resp.get_data(as_text=False)
        new_body = _inject_nav_html(body)
        if new_body is not body:
            resp.set_data(new_body)
            LOG.debug("nav injected (after mode)")
        return resp

    setattr(app, "_users_books_nav_inject_after", True)
    LOG.debug("navigation after_request handler registered")


class _NavPatchedLoader(BaseLoader):
    def __init__(self, wrapped: BaseLoader):  # type: ignore[override]
        self._wrapped = wrapped

    def get_source(self, environment, template):  # type: ignore[override]
        try:
            source, filename, uptodate = self._wrapped.get_source(environment, template)  # type: ignore[attr-defined]
        except TemplateNotFound:  # pragma: no cover
            raise
        try:
            new_source = source

            # 1) Admin nav links injection
            if PLUGIN_NAV_ID not in new_source and SEARCH_ANCHOR in new_source:
                anchor_pos = new_source.find(SEARCH_ANCHOR)
                if anchor_pos != -1:
                    close_pos = new_source.find('</li>', anchor_pos)
                    if close_pos != -1:
                        insertion_point = close_pos + len('</li>')
                        new_source = new_source[:insertion_point] + LINK_HTML_JINJA + new_source[insertion_point:]
                        LOG.debug("nav injected (loader) template=%s", template)

            # 2) Allow anonymous "Read in Browser" for free books
            # We patch upstream detail template in-memory to avoid copying the full template.
            if template == "detail.html":
                target = "{% if entry.reader_list and current_user.role_viewer() %}"
                if target in new_source:
                    replacement = (
                        "{% set ub_has_free_access = (g.catalog_state is defined and g.catalog_state and g.catalog_state.is_free(entry.id)) %}\n"
                        "{% if entry.reader_list and (current_user.role_viewer() or ub_has_free_access) %}"
                    )
                    new_source = new_source.replace(target, replacement, 1)
                    LOG.debug("detail.html patched for free-book anonymous read")

                # 3) Format Mozello price custom column and translate its label.
                # Calibre custom columns are rendered via `{{ c.name }}` and floats via `formatfloat(2)`.
                # For our `mz_price` column (display name "Price"), we want:
                # - Label translated (lv/ru/en)
                # - Value formatted like "€6,50" for lv/ru and "€6.50" for en
                label_target = "{{ c.name }}:"
                if label_target in new_source:
                    label_replacement = "{% if c.name == 'Price' %}{{ _('Price') }}:{% else %}{{ c.name }}:{% endif %}"
                    new_source = new_source.replace(label_target, label_replacement, 1)

                float_target = "{{ column.value|formatfloat(2) }}"
                if float_target in new_source:
                    float_replacement = "{% if c.name == 'Price' %}{{ column.value|format_eur }}{% else %}{{ column.value|formatfloat(2) }}{% endif %}"
                    new_source = new_source.replace(float_target, float_replacement, 1)
                    LOG.debug("detail.html patched for price formatting")

            # 4) Hide Discover (Random Books) for anonymous users.
            # Upstream sidebar item has id="rand" and may be publicly visible.
            if template == "layout.html":
                # 4a) Inject "Free" and "My Books" into the sidebar for non-admin users and
                # rewrite the "Books" link to point at /catalog/all-books.
                # This avoids client-side nav rebuilding (layout shift/jump on navigation).
                sidebar_item = (
                    '<li id="nav_{{element[\'id\']}}" {% if page == element[\'page\'] %}class="active"{% endif %}>'
                    '<a href="{{url_for(element[\'link\'], data=element[\'page\'], sort_param=\'stored\')}}">'
                    '<span class="glyphicon {{element[\'glyph\']}}"></span> {{_(element[\'text\'])}}'
                    '</a></li>'
                )
                if sidebar_item in new_source:
                    injected_prefix = (
                        '{% if g.catalog_state is defined and g.catalog_state and not g.catalog_state.is_admin and element[\'id\'] == "new" %}'
                        '<li id="nav_new" {% if request.path.startswith("/catalog/all-books") %}class="active"{% endif %}>'
                        '<a href="{{ url_for(\'catalog_scope.catalog_scope_all\') }}">'
                        '<span class="glyphicon {{element[\'glyph\']}}"></span> {{_(element[\'text\'])}}'
                        '</a></li>'
                        '<li id="nav_freebooks" {% if request.path.startswith("/catalog/free-books") %}class="active"{% endif %}>'
                        '<a href="{{ url_for(\'catalog_scope.catalog_scope_free\') }}">'
                        '<span class="glyphicon glyphicon-gift"></span> {{ _("Free") }}'
                        '</a></li>'
                        '{% if current_user.is_authenticated and not current_user.is_anonymous %}'
                        '<li id="nav_mybooks" {% if request.path.startswith("/catalog/my-books") %}class="active"{% endif %}>'
                        '<a href="{{ url_for(\'catalog_scope.catalog_scope_purchased\') }}">'
                        '<span class="glyphicon glyphicon-heart"></span> {{ _("My Books") }}'
                        '</a></li>'
                        '{% endif %}'
                        '{% else %}'
                    )
                    replacement = injected_prefix + sidebar_item + '{% endif %}'
                    new_source = new_source.replace(sidebar_item, replacement, 1)
                    LOG.debug("layout.html patched to inject scope nav items")

                target = "{% if current_user.check_visibility(element['visibility']) and element['public'] %}"
                if target in new_source:
                    replacement = (
                        "{% if current_user.check_visibility(element['visibility']) and element['public'] "
                        "and (element['id'] != 'rand' or current_user.is_authenticated) %}"
                    )
                    new_source = new_source.replace(target, replacement, 1)
                    LOG.debug("layout.html patched to hide random discover for anonymous")

            if template == "index.html":
                target = "{% if current_user.show_detail_random() and page != \"discover\" %}"
                if target in new_source:
                    replacement = "{% if current_user.is_authenticated and current_user.show_detail_random() and page != \"discover\" %}"
                    new_source = new_source.replace(target, replacement, 1)
                    LOG.debug("index.html patched to hide random section for anonymous")

            return new_source, filename, uptodate
        except Exception as exc:  # pragma: no cover
            LOG.debug("loader injection failed: %s", exc)
            return source, filename, uptodate


def register_loader_injection(app: Any) -> None:
    if getattr(app, "_users_books_nav_loader", False):  # type: ignore[attr-defined]
        return
    env = getattr(app, "jinja_env", None)
    if not env or not getattr(env, "loader", None):  # pragma: no cover
        return
    if isinstance(env.loader, _NavPatchedLoader):  # type: ignore[attr-defined]
        return
    env.loader = _NavPatchedLoader(env.loader)  # type: ignore[assignment]
    setattr(app, "_users_books_nav_loader", True)
    LOG.debug("navigation loader wrapper registered")


__all__ = [
    "register_response_injection",
    "register_loader_injection",
]
