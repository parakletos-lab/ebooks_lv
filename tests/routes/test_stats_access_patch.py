from __future__ import annotations

from functools import wraps

from flask import Flask

from app.routes.overrides.calibre_overrides import _patch_stats_public_access


def _login_required_stub(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapped


def test_patch_stats_public_access_unwraps_endpoint() -> None:
    app = Flask(__name__)

    def raw_stats():
        return "ok"

    app.view_functions["about.stats"] = _login_required_stub(raw_stats)

    _patch_stats_public_access(app)

    patched = app.view_functions["about.stats"]
    assert patched is raw_stats
    assert patched() == "ok"


def test_patch_stats_public_access_no_endpoint_is_safe() -> None:
    app = Flask(__name__)

    _patch_stats_public_access(app)

    assert "about.stats" not in app.view_functions
