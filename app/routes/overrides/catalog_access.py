"""Catalog filtering and UI asset injection for non-admin users.

This module implements a request-scoped "catalog scope" (all / purchased / free).
Historically scope was stored in session which unintentionally affected unrelated
pages (e.g. Authors list) because Calibre-Web reuses `CalibreDB.common_filters`
across many endpoints.

To avoid cross-page leakage, scope is now resolved per-request from the URL.
"""
from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, Optional

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    redirect,
    request,
    url_for,
)
try:  # pragma: no cover - Flask-Babel optional in tests
    from flask_babel import gettext as _babel_gettext  # type: ignore
except Exception:  # pragma: no cover
    _babel_gettext = None  # type: ignore


def _(message, **kwargs):  # type: ignore
    """Safe gettext wrapper.

    In some unit test setups `flask_babel` is importable but not configured on
    the Flask app, causing runtime KeyError when calling gettext.
    """

    if _babel_gettext is not None:
        try:
            return _babel_gettext(message, **kwargs)
        except Exception:
            pass
    if kwargs:
        try:
            return message % kwargs
        except Exception:
            return message
    return message
from urllib.parse import urlencode

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
    FREE = "free"


scope_bp = Blueprint("catalog_scope", __name__)


_SCOPED_PATH_PREFIXES: dict[str, CatalogScope] = {
    "/catalog/my-books": CatalogScope.PURCHASED,
    "/catalog/free-books": CatalogScope.FREE,
    "/catalog/all-books": CatalogScope.ALL,
}


def _match_scoped_prefix(path: str) -> Optional[str]:
    """Return the scoped prefix if this request should be scoped.

    Only the scope landing page and its internal sort/pagination URLs are scoped.
    Other URLs must behave like normal (unscoped) Calibre-Web pages.
    """

    if not path:
        return None
    for prefix in _SCOPED_PATH_PREFIXES.keys():
        if path == prefix:
            return prefix
        # Internal book-list navigation for the scoped landing page.
        if path.startswith(prefix + "/page/"):
            return prefix
        if path.startswith(prefix + "/newest/"):
            return prefix
    return None

# Book-list URLs that should NOT be rewritten when serving scoped book-list pages.
_REWRITE_EXCLUDED_FIRST_SEGMENTS = {
    "",
    "ajax",
    "app_static",
    "book",
    "cover",
    "download",
    "get_authors_json",
    "get_languages_json",
    "get_matching_tags",
    "get_publishers_json",
    "get_series_json",
    "get_tags_json",
    "login",
    "logout",
    "me",
    "mozello",
    "opds",
    "read",
    "register",
    "robots.txt",
    "series_cover",
    "show",
    "shelf",
    "static",
}

_REWRITE_TOP_LEVEL_PAGES = {
    "author",
    "publisher",
    "series",
    "ratings",
    "formats",
    "language",
    "category",
    "discover",
    "downloadlist",
}

_ATTR_REWRITE_RE = re.compile(r"(?P<attr>href|data-back)=(?P<q>['\"])(?P<url>/[^'\"]*)(?P=q)")


def _inject_scope_sidebar_nav(response: Response, payload: dict[str, Any]) -> None:
    """Inject scoped nav items into the left sidebar before JS runs.

    This prevents visible layout shift caused by client-side DOM insertion.
    """

    body_text = response.get_data(as_text=True)
    if not body_text:
        return

    # Only inject if sidebar exists.
    if 'id="scnd-nav"' not in body_text and "id='scnd-nav'" not in body_text:
        return

    # Prevent Intention.js from re-parenting/rebuilding the sidebar on load.
    # This reduces visible sidebar "jump" when navigating between pages.
    try:
        ul_re = re.compile(r"<ul(?P<attrs>[^>]*)>", re.IGNORECASE)

        def _strip_intent_attrs(match: re.Match[str]) -> str:
            attrs = match.group("attrs")
            if "scnd-nav" not in attrs:
                return match.group(0)
            cleaned = attrs
            cleaned = re.sub(r"\sintent\b", "", cleaned)
            cleaned = re.sub(r"\sin-[a-zA-Z-]+=(\"[^\"]*\"|'[^']*')", "", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).rstrip()
            return f"<ul{cleaned}>"

        body_text = ul_re.sub(_strip_intent_attrs, body_text)
    except Exception:
        pass

    views = payload.get("views") or {}
    scope_labels = payload.get("scope_labels") or {}
    allow_my_books = bool(payload.get("allow_my_books"))

    all_href = views.get("all_url") or "/catalog/all-books"
    free_href = views.get("free_url") or "/catalog/free-books"
    purchased_href = views.get("purchased_url") or "/catalog/my-books"

    free_label = scope_labels.get("free") or "Free"
    purchased_label = scope_labels.get("purchased") or "My Books"

    # If already present, do nothing.
    if 'id="nav_freebooks"' in body_text:
        # Still ensure Books points to /catalog/all-books.
        pass

    current = (views.get("current") or "all")
    free_active = ' class="active"' if current == CatalogScope.FREE.value else ""
    purchased_active = ' class="active"' if current == CatalogScope.PURCHASED.value else ""

    free_li = (
        f'<li id="nav_freebooks"{free_active}>'
        f'<a href="{free_href}"><span class="glyphicon glyphicon-gift"></span> {free_label}</a></li>'
    )
    purchased_li = (
        f'<li id="nav_mybooks"{purchased_active}>'
        f'<a href="{purchased_href}"><span class="glyphicon glyphicon-heart"></span> {purchased_label}</a></li>'
    )

    # Rewrite Books sidebar link to point to /catalog/all-books.
    # Handle both single and double quotes and additional attributes.
    try:
        body_text = re.sub(
            r"(<li[^>]*id=['\"]nav_new['\"][^>]*>.*?<a[^>]*href=)(['\"])([^'\"]*)(\2)",
            rf"\1\2{all_href}\4",
            body_text,
            count=1,
            flags=re.DOTALL,
        )
    except Exception:
        pass

    if 'id="nav_freebooks"' not in body_text:
        inserted = False

        # Prefer inserting immediately after the Books nav item.
        marker = 'id="nav_new"'
        pos = body_text.find(marker)
        if pos != -1:
            close_pos = body_text.find("</li>", pos)
            if close_pos != -1:
                insertion_point = close_pos + len("</li>")
                addition = free_li + (purchased_li if allow_my_books else "")
                body_text = body_text[:insertion_point] + addition + body_text[insertion_point:]
                inserted = True

        # Fallback: insert right after the "Browse" header list item.
        if not inserted:
            nav_pos = body_text.find('id="scnd-nav"')
            if nav_pos != -1:
                first_li_end = body_text.find("</li>", nav_pos)
                if first_li_end != -1:
                    insertion_point = first_li_end + len("</li>")
                    addition = free_li + (purchased_li if allow_my_books else "")
                    body_text = body_text[:insertion_point] + addition + body_text[insertion_point:]

    response.set_data(body_text)


def _safe_redirect_target(default: str) -> str:
    candidate = request.args.get("next")
    if candidate and candidate.startswith("/"):
        return candidate
    return default


def _login_redirect(next_target: str) -> Response:
    try:
        login_path = url_for("login_override.login_page", next=next_target)
    except Exception:
        login_path = "/login?" + urlencode({"next": next_target})
    return redirect(login_path)


def _current_catalog_state() -> Optional[UserCatalogState]:
    state = getattr(g, "catalog_state", None)
    if isinstance(state, UserCatalogState):
        return state
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
    return state


def _require_authenticated_scope(endpoint_name: str) -> Optional[Response]:
    state = _current_catalog_state()
    if isinstance(state, UserCatalogState) and (state.is_admin or state.is_authenticated):
        return None
    try:
        next_target = url_for(endpoint_name)
    except Exception:
        next_target = request.path or "/"
    return _login_redirect(next_target)


def _dispatch_calibre_endpoint(endpoint: str, **kwargs: Any) -> Response:
    view = current_app.view_functions.get(endpoint)
    if not callable(view):
        return redirect("/")
    return view(**kwargs)  # type: ignore[misc]


def _render_scoped_index(scope: CatalogScope, page: int) -> Response:
    g.catalog_scope = scope
    return _dispatch_calibre_endpoint("web.index", page=page)


def _render_scoped_books_list(scope: CatalogScope, data: str, sort_param: str, book_id: str, page: int) -> Response:
    g.catalog_scope = scope
    return _dispatch_calibre_endpoint(
        "web.books_list",
        data=data,
        sort_param=sort_param,
        book_id=book_id,
        page=page,
    )


@scope_bp.route("/catalog/my-books", defaults={"page": 1}, methods=["GET"])
@scope_bp.route("/catalog/my-books/page/<int:page>", methods=["GET"])
def catalog_scope_purchased(page: int):
    # Page is served directly; scope is request-local (no session persistence).
    return _render_scoped_index(CatalogScope.PURCHASED, page)


@scope_bp.route("/catalog/my-books/newest/<sort_param>", defaults={"page": 1, "book_id": "1"}, methods=["GET"])
@scope_bp.route("/catalog/my-books/newest/<sort_param>/", defaults={"page": 1, "book_id": "1"}, methods=["GET"])
@scope_bp.route("/catalog/my-books/newest/<sort_param>/<book_id>", defaults={"page": 1}, methods=["GET"])
@scope_bp.route("/catalog/my-books/newest/<sort_param>/<book_id>/<int:page>", methods=["GET"])
def catalog_scope_purchased_list(sort_param: str, book_id: str, page: int):
    return _render_scoped_books_list(CatalogScope.PURCHASED, "newest", sort_param, book_id, page)


@scope_bp.route("/catalog/my-books/<path:rest>", methods=["GET"])
def catalog_scope_purchased_passthrough(rest: str):
    # Only the My Books landing page is filtered; all other pages behave normally.
    target = "/" + (rest or "")
    if request.query_string:
        target = target + "?" + request.query_string.decode("utf-8", errors="ignore")
    return redirect(target)


@scope_bp.route("/catalog/all-books", defaults={"page": 1}, methods=["GET"])
@scope_bp.route("/catalog/all-books/page/<int:page>", methods=["GET"])
def catalog_scope_all(page: int):
    return _render_scoped_index(CatalogScope.ALL, page)


@scope_bp.route("/catalog/all-books/newest/<sort_param>", defaults={"page": 1, "book_id": "1"}, methods=["GET"])
@scope_bp.route("/catalog/all-books/newest/<sort_param>/", defaults={"page": 1, "book_id": "1"}, methods=["GET"])
@scope_bp.route("/catalog/all-books/newest/<sort_param>/<book_id>", defaults={"page": 1}, methods=["GET"])
@scope_bp.route("/catalog/all-books/newest/<sort_param>/<book_id>/<int:page>", methods=["GET"])
def catalog_scope_all_list(sort_param: str, book_id: str, page: int):
    return _render_scoped_books_list(CatalogScope.ALL, "newest", sort_param, book_id, page)


@scope_bp.route("/catalog/all-books/<path:rest>", methods=["GET"])
def catalog_scope_all_passthrough(rest: str):
    target = "/" + (rest or "")
    if request.query_string:
        target = target + "?" + request.query_string.decode("utf-8", errors="ignore")
    return redirect(target)


@scope_bp.route("/catalog/free-books", defaults={"page": 1}, methods=["GET"])
@scope_bp.route("/catalog/free-books/page/<int:page>", methods=["GET"])
def catalog_scope_free(page: int):
    return _render_scoped_index(CatalogScope.FREE, page)


@scope_bp.route("/catalog/free-books/newest/<sort_param>", defaults={"page": 1, "book_id": "1"}, methods=["GET"])
@scope_bp.route("/catalog/free-books/newest/<sort_param>/", defaults={"page": 1, "book_id": "1"}, methods=["GET"])
@scope_bp.route("/catalog/free-books/newest/<sort_param>/<book_id>", defaults={"page": 1}, methods=["GET"])
@scope_bp.route("/catalog/free-books/newest/<sort_param>/<book_id>/<int:page>", methods=["GET"])
def catalog_scope_free_list(sort_param: str, book_id: str, page: int):
    return _render_scoped_books_list(CatalogScope.FREE, "newest", sort_param, book_id, page)


@scope_bp.route("/catalog/free-books/<path:rest>", methods=["GET"])
def catalog_scope_free_passthrough(rest: str):
    # Only the Free landing page is filtered; all other pages behave normally.
    target = "/" + (rest or "")
    if request.query_string:
        target = target + "?" + request.query_string.decode("utf-8", errors="ignore")
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
    payload["buy_label"] = _("Buy Online")
    payload["cart_icon_class"] = "eblv-icon-cart"
    payload["allow_my_books"] = bool(state.is_authenticated)
    payload["scope_labels"] = {
        "purchased": _("My Books"),
        "all": _("All Books"),
        "free": _("Free"),
    }
    payload["views"] = {
        "current": scope.value,
        "purchased_url": url_for("catalog_scope.catalog_scope_purchased"),
        "all_url": url_for("catalog_scope.catalog_scope_all"),
        "free_url": url_for("catalog_scope.catalog_scope_free"),
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
        safe_payload = payload_json.replace("</", "<\\/")
        script_tags = (
            f'<script id="{CATALOG_STATE_SCRIPT_ID}" type="application/json">{safe_payload}</script>'
            f'<script src="{js_href}" {JS_INJECT_MARKER}="1"></script>'
        )
        if "</body>" in body_text:
            body_text = body_text.replace("</body>", f"{script_tags}</body>", 1)
    response.set_data(body_text)


def _resolve_scope(state: UserCatalogState) -> CatalogScope:
    if state.is_admin:
        return CatalogScope.ALL

    path = request.path or "/"
    matched = _match_scoped_prefix(path)
    if matched:
        return _SCOPED_PATH_PREFIXES[matched]
    return CatalogScope.ALL


def _rewrite_scoped_book_list_links(response: Response, scope_prefix: str) -> None:
    if not scope_prefix or not scope_prefix.startswith("/catalog/"):
        return
    body_text = response.get_data(as_text=True)
    if not body_text:
        return

    def _rewrite_url(url: str) -> str:
        if not url or not url.startswith("/"):
            return url
        if url.startswith(scope_prefix + "/") or url == scope_prefix:
            return url
        if url == "/":
            return url

        # Keep other scoped pages and admin areas untouched.
        if url.startswith("/catalog/"):
            return url

        # Split off any query/fragment while keeping absolute-path URLs.
        # url always startswith '/', so simplest is to cut at first ?/#.
        cut = len(url)
        for sep in ("?", "#"):
            idx = url.find(sep)
            if idx != -1:
                cut = min(cut, idx)
        path = url[:cut]
        suffix = url[cut:]

        segments = [seg for seg in path.split("/") if seg]
        if not segments:
            return url

        # Only keep the scoped landing page's sort/pagination inside the scoped prefix.
        # Everything else (hot/rated/unread/discover/authors/etc) must behave like normal pages.
        first = segments[0]
        if first not in {"newest", "page"}:
            return url
        if len(segments) == 1:
            return url
        if first in _REWRITE_EXCLUDED_FIRST_SEGMENTS:
            return url
        if first in _REWRITE_TOP_LEVEL_PAGES and len(segments) == 1:
            return url

        return f"{scope_prefix}{path}{suffix}"

    def _sub(match: re.Match[str]) -> str:
        attr = match.group("attr")
        quote = match.group("q")
        original = match.group("url")
        updated = _rewrite_url(original)
        return f"{attr}={quote}{updated}{quote}"

    rewritten = _ATTR_REWRITE_RE.sub(_sub, body_text)
    if rewritten != body_text:
        response.set_data(rewritten)


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

        # Enforce that "My Books" landing/sort pages require authentication (scope is URL-based).
        try:
            path = request.path or ""
            if _match_scoped_prefix(path) == "/catalog/my-books" and not state.is_authenticated:
                next_target = request.full_path or request.path or "/"
                if next_target.endswith("?"):
                    next_target = request.path or "/"
                return _login_redirect(next_target)
        except Exception:
            pass

        scope = _resolve_scope(state)
        g.catalog_scope = scope
        payload = _build_payload(state, scope)
        g.catalog_payload = payload
        if request.endpoint == "web.read_book":
            book_id = None
            if request.view_args:
                book_id = request.view_args.get("book_id")
            if not state.is_purchased(book_id) and not state.is_free(book_id):
                LOG.debug("Blocking reader access for non-purchased book_id=%s", book_id)
                return redirect(url_for("web.show_book", book_id=book_id))
        return None

    @app.after_request  # type: ignore[misc]
    def _catalog_after_request(response: Response):
        state = getattr(g, "catalog_state", None)
        payload = getattr(g, "catalog_payload", None)
        if not isinstance(state, UserCatalogState) or state.is_admin or not payload:
            return response
        if not _should_inject(response):
            return response

        # Make sidebar stable on first paint (avoid client-side nav rebuild/jump).
        try:
            _inject_scope_sidebar_nav(response, payload)
        except Exception:
            LOG.debug("Scope sidebar injection failed", exc_info=True)

        # Keep scoped book-list navigation inside its scoped prefix.
        try:
            matched = _match_scoped_prefix(request.path or "")
            if matched:
                _rewrite_scoped_book_list_links(response, matched)
        except Exception:
            LOG.debug("Scoped link rewrite failed", exc_info=True)

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
