"""Template-based navigation link insertion (layout.html loader patch).

This avoids HTML after_request mutation by wrapping the Jinja loader and
injecting a single <li> link (ebooks.lv) for admin users only into the
main navigation bar (layout.html) immediately after the Admin link.

Insertion heuristic:
  - Target template name: 'layout.html'
  - Require presence of admin anchor id="top_admin"
  - Skip if our id already present (id="top_users_books")

The injection produces Jinja-guarded snippet so non-admin users never see
an orphan li element even if future layout changes move the Admin link.

Kept intentionally small & idempotent.
"""
from __future__ import annotations

from typing import Any
from jinja2 import BaseLoader, TemplateNotFound

from .logging_setup import get_logger

LOG = get_logger()

_ADMIN_ANCHOR = 'id="top_admin"'
_PLUGIN_ANCHOR = 'id="top_users_books"'

_SNIPPET = (
    '{% if current_user and current_user.role_admin() %}'
    '<li><a id="top_users_books" data-text="ebooks.lv" '
    'href="/plugin/users_books/admin/ui">'
    '<span class="glyphicon glyphicon-book"></span> '
    '<span class="hidden-sm">ebooks.lv</span></a></li>'
    '{% endif %}'
)


class _LayoutPatchedLoader(BaseLoader):
    def __init__(self, wrapped: BaseLoader):  # type: ignore[override]
        self._wrapped = wrapped

    def get_source(self, environment, template):  # type: ignore[override]
        try:
            source, filename, uptodate = self._wrapped.get_source(environment, template)  # type: ignore[attr-defined]
        except TemplateNotFound:
            raise
        if template != 'layout.html':
            return source, filename, uptodate
        if _PLUGIN_ANCHOR in source or _ADMIN_ANCHOR not in source:
            return source, filename, uptodate
        try:
            anchor_pos = source.find(_ADMIN_ANCHOR)
            if anchor_pos == -1:
                return source, filename, uptodate
            # find closing </li> after admin anchor
            close_pos = source.find('</li>', anchor_pos)
            if close_pos == -1:
                return source, filename, uptodate
            insert_at = close_pos + len('</li>')
            new_source = source[:insert_at] + _SNIPPET + source[insert_at:]
            LOG.debug('users_books nav template snippet injected (layout.html)')
            return new_source, filename, uptodate
        except Exception as exc:  # pragma: no cover
            LOG.debug('users_books nav template injection failed: %s', exc)
            return source, filename, uptodate


def register_nav_template_loader(app: Any) -> None:
    if getattr(app, '_users_books_nav_loader', False):  # type: ignore[attr-defined]
        return
    env = getattr(app, 'jinja_env', None)
    if not env or not getattr(env, 'loader', None):
        return
    if isinstance(env.loader, _LayoutPatchedLoader):
        return
    env.loader = _LayoutPatchedLoader(env.loader)  # type: ignore[assignment]
    setattr(app, '_users_books_nav_loader', True)
    LOG.debug('users_books: nav template loader registered')


__all__ = ['register_nav_template_loader']
