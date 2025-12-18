"""Ensure language switch assets land on pages that override blocks.

If a template overrides ``block js`` without calling ``super()``, the layout
injection can be skipped. This after_request hook appends the config payload,
style, and JS loader when the marker is missing so the language switch remains
available across all Calibre-Web pages.
"""
from __future__ import annotations

from typing import Any, Tuple

from flask import Response, session, url_for

from app.utils.logging import get_logger

LOG = get_logger("language_switch_injection")

MARKER = 'id="ub-config"'
MAX_BODY_SIZE = 1_500_000  # bytes


def _is_admin() -> bool:
    try:
        from app.utils.identity import is_admin_user  # lazy import to avoid bootstrap failures
        return bool(is_admin_user())
    except Exception:
        return False


def _active_language() -> str:
    preferred = session.get("ub_preferred_locale")
    if preferred:
        return str(preferred)
    try:
        from cps import ub  # type: ignore
        cu = getattr(ub, "current_user", None)
        if cu and not getattr(cu, "is_anonymous", False):
            locale = getattr(cu, "locale", None)
            if locale:
                return str(locale)
    except Exception:
        pass
    return "lv"


def _is_anonymous() -> bool:
    try:
        from cps import ub  # type: ignore
        cu = getattr(ub, "current_user", None)
        return bool(cu and getattr(cu, "is_anonymous", False))
    except Exception:
        return False


def _should_skip(response: Response) -> Tuple[bool, str]:
    if response.status_code != 200:
        return True, f"status_{response.status_code}"
    ctype = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in ctype:
        return True, f"ctype_{ctype or 'none'}"
    body = response.get_data(as_text=False)
    if not body:
        return True, "empty"
    if len(body) > MAX_BODY_SIZE:
        return True, "too_large"
    if MARKER.encode("utf-8") in body:
        return True, "already_has_marker"
    return False, "ok"


def _build_snippet() -> str:
    switch_url = url_for("language_switch.switch_language")
    script_src = url_for("_app_templates.static", filename="js/ub_lang_switch.js")
    css_href = url_for("_app_templates.static", filename="css/ub_shared.css")
    try:
        from flask import request  # type: ignore
        login_url = url_for("web.login", next=(getattr(request, "full_path", "/") or "/").rstrip("?"))
    except Exception:
        login_url = url_for("web.login")
    login_label = "Login"
    active_lang = _active_language()
    is_admin = "1" if _is_admin() else "0"
    is_anon = "1" if _is_anonymous() else "0"
    css_link = f'<link rel="stylesheet" href="{css_href}" />'
    config_div = (
        f'<div id="ub-config" data-is-admin="{is_admin}" data-is-anon="{is_anon}" '
        f'data-switch-url="{switch_url}" data-active-lang="{active_lang}" '
        f'data-login-url="{login_url}" data-login-label="{login_label}" hidden></div>'
    )
    script_tag = f'<script src="{script_src}"></script>'
    return css_link + config_div + script_tag


def _inject(response: Response) -> Response:
    body = response.get_data(as_text=False)
    if not body:
        return response
    lower_body = body.lower()
    closing = lower_body.rfind(b"</body>")
    snippet = _build_snippet().encode("utf-8")
    if closing == -1:
        response.set_data(body + snippet)
        return response
    response.set_data(body[:closing] + snippet + body[closing:])
    return response


def register_language_switch_injection(app: Any) -> None:
    if getattr(app, "_ub_lang_switch_injected", False):  # type: ignore[attr-defined]
        return

    @app.after_request  # type: ignore[misc]
    def _lang_switch_after(resp: Response):  # type: ignore[override]
        skip, reason = _should_skip(resp)
        if skip:
            LOG.debug("lang switch after_request skip: %s", reason)
            return resp
        return _inject(resp)

    setattr(app, "_ub_lang_switch_injected", True)
    LOG.debug("language switch after_request hook registered")


__all__ = ["register_language_switch_injection"]
