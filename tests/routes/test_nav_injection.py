from __future__ import annotations

from jinja2 import BaseLoader

from app.routes.overrides.nav_injection import _NavPatchedLoader


class _StaticLoader(BaseLoader):
    def __init__(self, source: str):
        self._source = source

    def get_source(self, environment, template):  # type: ignore[override]
        return self._source, template, lambda: True


def _patch_layout(source: str) -> str:
    loader = _NavPatchedLoader(_StaticLoader(source))
    patched, _, _ = loader.get_source(None, "layout.html")
    return patched


def test_layout_about_link_visible_for_anonymous_users() -> None:
    source = """
{% if not current_user.is_anonymous %}
                <li id="nav_createshelf" class="create-shelf"><a href="{{url_for('shelf.create_shelf')}}">{{_('Create a Shelf')}}</a></li>
                <li id="nav_about" {% if page == 'stat' %}class="active"{% endif %}><a href="{{url_for('about.stats')}}"><span class="glyphicon glyphicon-info-sign"></span> {{_('About')}}</a></li>
              {% endif %}
    {% for message in get_flashed_messages(with_categories=True) %}
"""

    patched = _patch_layout(source)

    assert "<li id=\"nav_createshelf\"" in patched
    assert "{% if not current_user.is_anonymous %}" in patched
    assert "{% endif %}\n              <li id=\"nav_about\"" in patched
    assert "ub-eu-notice" not in patched


def test_layout_leaves_flash_loop_untouched() -> None:
    source = """
    {% for message in get_flashed_messages(with_categories=True) %}
"""

    patched = _patch_layout(source)

    assert "{% for message in get_flashed_messages(with_categories=True) %}" in patched
