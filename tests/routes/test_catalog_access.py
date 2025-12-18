"""Tests for catalog scope routes enforcing authentication."""
from __future__ import annotations

import pytest
from flask import Flask

from app.routes.overrides import catalog_access
from app.routes.overrides.catalog_access import CatalogScope, register_catalog_access
from app.services.catalog_access import UserCatalogState


@pytest.fixture
def catalog_app(monkeypatch):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "catalog-test"

    state_holder: dict[str, UserCatalogState] = {
        "state": UserCatalogState(is_admin=False, is_authenticated=False)
    }

    def fake_is_admin() -> bool:
        return state_holder["state"].is_admin

    def fake_build_catalog_state(**_kwargs):
        return state_holder["state"]

    monkeypatch.setattr(catalog_access, "is_admin_user", fake_is_admin)
    monkeypatch.setattr(catalog_access, "build_catalog_state", fake_build_catalog_state)

    app.add_url_rule("/", endpoint="web.index", view_func=lambda page=1: "ok")
    app.add_url_rule("/page/<int:page>", endpoint="web.index_page", view_func=lambda page: "ok")
    app.add_url_rule(
        "/<data>/<sort_param>",
        endpoint="web.books_list",
        view_func=lambda data, sort_param, book_id="1", page=1: "ok",
    )

    register_catalog_access(app)
    app.state_holder = state_holder  # type: ignore[attr-defined]
    return app


@pytest.fixture
def client(catalog_app):
    return catalog_app.test_client()


def test_catalog_my_books_requires_login(catalog_app, client):
    catalog_app.state_holder["state"] = UserCatalogState(is_admin=False, is_authenticated=False)  # type: ignore[attr-defined]

    resp = client.get("/catalog/my-books")

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login?next=%2Fcatalog%2Fmy-books")


def test_catalog_routes_allow_authenticated_user(catalog_app, client):
    catalog_app.state_holder["state"] = UserCatalogState(is_admin=False, is_authenticated=True)  # type: ignore[attr-defined]

    resp = client.get("/catalog/my-books")
    assert resp.status_code == 200

    resp = client.get("/catalog/all-books")
    assert resp.status_code == 200


def test_catalog_all_books_allows_anonymous_user(catalog_app, client):
    catalog_app.state_holder["state"] = UserCatalogState(is_admin=False, is_authenticated=False)  # type: ignore[attr-defined]

    resp = client.get("/catalog/all-books")

    # Scope pages are served directly; they do not set session scope.
    assert resp.status_code == 200


def test_catalog_my_books_does_not_scope_other_pages(catalog_app, client):
    """Only /catalog/my-books itself is scoped; other pages must remain unscoped."""

    catalog_app.state_holder["state"] = UserCatalogState(is_admin=False, is_authenticated=False)  # type: ignore[attr-defined]

    resp = client.get("/catalog/my-books/rated/stored/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/rated/stored/")


def test_catalog_free_books_does_not_scope_other_pages(catalog_app, client):
    """Only /catalog/free-books itself is scoped; other pages must remain unscoped."""

    catalog_app.state_holder["state"] = UserCatalogState(is_admin=False, is_authenticated=False)  # type: ignore[attr-defined]

    resp = client.get("/catalog/free-books/unread/stored/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/unread/stored/")
