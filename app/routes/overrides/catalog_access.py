"""Catalog filtering and UI asset injection for non-admin users."""
from __future__ import annotations

import json
from enum import Enum
from typing import Any, Optional

from flask import (
    Blueprint,
    Response,
    g,
    redirect,
    request,
    session,
    url_for,
)

from app.services.catalog_access import UserCatalogState, build_catalog_state
from app.utils.identity import (
    get_current_user_email,
    get_current_user_id,
    is_admin_user,
)
from app.utils.logging import get_logger

LOG = get_logger("catalog_access")

CATALOG_STATE_SCRIPT_ID = "mozello-catalog-state"
CSS_INJECT_MARKER = "data-eblv-catalog-css"
JS_INJECT_MARKER = "data-eblv-catalog-js"
MAX_RESPONSE_SIZE = 2_000_000  # bytes
CATALOG_SCOPE_SESSION_KEY = "catalog_scope"


class CatalogScope(str, Enum):
    ALL = "all"
    PURCHASED = "purchased"


scope_bp = Blueprint("catalog_scope", __name__)


def _safe_redirect_target(default: str) -> str:
    candidate = request.args.get("next")
    if candidate and candidate.startswith("/"):
        return candidate
    return default


@scope_bp.route("/catalog/my-books", methods=["GET"])
def catalog_scope_purchased():
    session[CATALOG_SCOPE_SESSION_KEY] = CatalogScope.PURCHASED.value
    target = _safe_redirect_target(url_for("web.index"))
    return redirect(target)


@scope_bp.route("/catalog/all-books", methods=["GET"])
def catalog_scope_all():
    session[CATALOG_SCOPE_SESSION_KEY] = CatalogScope.ALL.value
    target = _safe_redirect_target(url_for("web.index"))
    return redirect(target)


def _build_payload(state: UserCatalogState, scope: CatalogScope) -> Optional[dict[str, Any]]:
    if state.is_admin:
        return None
    try:
        sample_url = url_for("mozello_webhook.mozello_product_redirect", mz_handle="__HANDLE__")
        mozello_base = sample_url.replace("__HANDLE__", "")
    except Exception:
        mozello_base = "/mozello/books/"
    payload = state.to_payload()
    payload["mozello_base"] = mozello_base
    payload["buy_label"] = "Buy Online"
    payload["cart_icon_class"] = "glyphicon-shopping-cart"
    payload["views"] = {
        "current": scope.value,
        "purchased_url": url_for("catalog_scope.catalog_scope_purchased"),
        "all_url": url_for("catalog_scope.catalog_scope_all"),
    }
    return payload


def _should_inject(response: Response) -> bool:
    if response.status_code != 200:
        return False
    ctype = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in ctype:
        return False
    body = response.get_data(as_text=False)
    if not body or len(body) > MAX_RESPONSE_SIZE:
        return False
    return True


def _insert_assets(response: Response, payload: dict[str, Any]) -> None:
    body_text = response.get_data(as_text=True)
    if not body_text:
        return
    if CSS_INJECT_MARKER not in body_text:
        try:
            css_href = url_for("_app_templates.static", filename="catalog/non_admin_catalog.css")
        except Exception:
            css_href = "/app_static/catalog/non_admin_catalog.css"
        css_tag = f'<link rel="stylesheet" href="{css_href}" {CSS_INJECT_MARKER}="1">'
        if "</head>" in body_text:
            body_text = body_text.replace("</head>", f"{css_tag}</head>", 1)
    if CATALOG_STATE_SCRIPT_ID not in body_text:
        try:
            js_href = url_for("_app_templates.static", filename="catalog/non_admin_catalog.js")
        except Exception:
            js_href = "/app_static/catalog/non_admin_catalog.js"
        try:
            payload_json = json.dumps(payload)
        except Exception:
            LOG.debug("Failed to serialize catalog payload", exc_info=True)
            return
        safe_payload = payload_json.replace("</", "<\/")
        script_tags = (
            f'<script id="{CATALOG_STATE_SCRIPT_ID}" type="application/json">{safe_payload}</script>'
            f'<script src="{js_href}" {JS_INJECT_MARKER}="1"></script>'
        )
        if "</body>" in body_text:
            body_text = body_text.replace("</body>", f"{script_tags}</body>", 1)
    response.set_data(body_text)


def _resolve_scope(state: UserCatalogState) -> CatalogScope:
    if state.is_admin:
        session[CATALOG_SCOPE_SESSION_KEY] = CatalogScope.ALL.value
        return CatalogScope.ALL
    stored = session.get(CATALOG_SCOPE_SESSION_KEY)
    if isinstance(stored, str):
        try:
            return CatalogScope(stored)
        except ValueError:
            pass
    session[CATALOG_SCOPE_SESSION_KEY] = CatalogScope.ALL.value
    return CatalogScope.ALL


def register_catalog_access(app: Any) -> None:
    if getattr(app, "_users_books_catalog_hooks", False):  # type: ignore[attr-defined]
        return

    @app.before_request  # type: ignore[misc]
    def _catalog_before_request():
        try:
            admin = is_admin_user()
        except Exception:
            admin = False
        state = build_catalog_state(
            calibre_user_id=get_current_user_id(),
            email=get_current_user_email(),
            is_admin=admin,
        )
        g.catalog_state = state
        if state.is_admin:
            g.catalog_payload = None
            g.catalog_scope = CatalogScope.ALL
            return None
        scope = _resolve_scope(state)
        g.catalog_scope = scope
        payload = _build_payload(state, scope)
        g.catalog_payload = payload
        if request.endpoint == "web.read_book":
            book_id = None
            if request.view_args:
                book_id = request.view_args.get("book_id")
            if not state.is_purchased(book_id):
                LOG.debug("Blocking reader access for non-purchased book_id=%s", book_id)
                return redirect(url_for("web.index"))
        return None

    @app.after_request  # type: ignore[misc]
    def _catalog_after_request(response: Response):
        state = getattr(g, "catalog_state", None)
        payload = getattr(g, "catalog_payload", None)
        if not isinstance(state, UserCatalogState) or state.is_admin or not payload:
            return response
        if not _should_inject(response):
            return response
        _insert_assets(response, payload)
        return response

    if not getattr(app, "_catalog_scope_bp", False):  # type: ignore[attr-defined]
        app.register_blueprint(scope_bp)
        setattr(app, "_catalog_scope_bp", True)
        LOG.debug("Catalog scope blueprint registered")

    setattr(app, "_users_books_catalog_hooks", True)
    LOG.debug("Catalog access hooks registered")


__all__ = [
    "register_catalog_access",
    "UserCatalogState",
    "CatalogScope",
]
