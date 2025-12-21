from __future__ import annotations

from pathlib import Path

import pytest
from flask import Flask
from jinja2 import ChoiceLoader, FileSystemLoader

from app.routes.admin_mozello import register_blueprints
from app.routes import admin_mozello


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_TEMPLATES = PROJECT_ROOT / "app" / "templates"
CALIBRE_TEMPLATES = PROJECT_ROOT / "calibre-web" / "cps" / "templates"
APP_PACKAGE_ROOT = PROJECT_ROOT / "app"


@pytest.fixture
def flask_app():
    app = Flask(__name__, template_folder=str(APP_TEMPLATES))
    app.jinja_loader = ChoiceLoader([
        FileSystemLoader(str(APP_TEMPLATES)),
        FileSystemLoader(str(APP_PACKAGE_ROOT)),
        FileSystemLoader(str(CALIBRE_TEMPLATES)),
    ])
    app.config["SECRET_KEY"] = "mozello-test-secret"
    register_blueprints(app)
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


def test_product_changed_stores_pictures_and_seeds_cover_uid(monkeypatch, client):
    payload = {
        "event": "PRODUCT_CHANGED",
        "product": {
            "handle": "book-6",
            "pictures": [
                {"uid": "uid-7779842", "url": "https://example.test/a.jpg"},
                {"uid": "uid-7803633", "url": "https://example.test/b.jpg"},
            ],
            "price": 12.12,
            "sale_price": None,
            "full_url": {"en": "/item/book-6/"},
        },
    }

    monkeypatch.setattr(admin_mozello.mozello_service, "handle_webhook", lambda raw, headers: (True, "PRODUCT_CHANGED", payload))
    monkeypatch.setattr(admin_mozello.mozello_service, "derive_relative_url_from_product", lambda product, **_: "/item/book-6/")

    calls = {"pictures": None, "cover": None}

    monkeypatch.setattr(admin_mozello.books_sync, "lookup_book_by_handle", lambda handle: {"book_id": 6, "language_code": "en"})
    monkeypatch.setattr(admin_mozello.books_sync, "set_mz_relative_url_for_handle", lambda handle, url: True)
    monkeypatch.setattr(admin_mozello.books_sync, "clear_mz_relative_url_for_handle", lambda handle: True)
    monkeypatch.setattr(admin_mozello.books_sync, "set_mz_price_for_handle", lambda handle, price: True)

    # Empty existing cover uids triggers seeding.
    monkeypatch.setattr(admin_mozello.books_sync, "get_mz_cover_picture_uids_for_handle", lambda handle: [])

    def _set_cover(handle, uids):
        calls["cover"] = (handle, uids)
        return True

    def _set_pics(handle, pictures):
        calls["pictures"] = (handle, pictures)
        return True

    monkeypatch.setattr(admin_mozello.books_sync, "set_mz_cover_picture_uids_for_handle", _set_cover)
    monkeypatch.setattr(admin_mozello.books_sync, "set_mz_pictures_for_handle", _set_pics)

    resp = client.post("/mozello/webhook", data=b"{}", headers={"X-Mozello-Test": "unsigned"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["pictures_stored"] is True
    assert body["cover_seeded"] is True
    assert calls["pictures"][0] == "book-6"
    assert calls["cover"] == ("book-6", ["uid-7779842"])  # first Mozello picture


def test_product_changed_does_not_overwrite_existing_cover_tracking(monkeypatch, client):
    payload = {
        "event": "PRODUCT_CHANGED",
        "product": {
            "handle": "book-6",
            "pictures": [
                {"uid": "uid-7779842", "url": "https://example.test/a.jpg"},
                {"uid": "uid-7803633", "url": "https://example.test/b.jpg"},
            ],
            "price": 12.12,
            "sale_price": None,
            "full_url": {"en": "/item/book-6/"},
        },
    }

    monkeypatch.setattr(admin_mozello.mozello_service, "handle_webhook", lambda raw, headers: (True, "PRODUCT_CHANGED", payload))
    monkeypatch.setattr(admin_mozello.mozello_service, "derive_relative_url_from_product", lambda product, **_: "/item/book-6/")

    monkeypatch.setattr(admin_mozello.books_sync, "lookup_book_by_handle", lambda handle: {"book_id": 6, "language_code": "en"})
    monkeypatch.setattr(admin_mozello.books_sync, "set_mz_relative_url_for_handle", lambda handle, url: True)
    monkeypatch.setattr(admin_mozello.books_sync, "clear_mz_relative_url_for_handle", lambda handle: True)
    monkeypatch.setattr(admin_mozello.books_sync, "set_mz_price_for_handle", lambda handle, price: True)

    # Existing cover uids => no seeding.
    monkeypatch.setattr(admin_mozello.books_sync, "get_mz_cover_picture_uids_for_handle", lambda handle: ["uid-existing"])

    cover_calls = {"count": 0}

    def _set_cover(handle, uids):
        cover_calls["count"] += 1
        return True

    monkeypatch.setattr(admin_mozello.books_sync, "set_mz_cover_picture_uids_for_handle", _set_cover)
    monkeypatch.setattr(admin_mozello.books_sync, "set_mz_pictures_for_handle", lambda handle, pictures: True)

    resp = client.post("/mozello/webhook", data=b"{}", headers={"X-Mozello-Test": "unsigned"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["cover_seeded"] is False
    assert cover_calls["count"] == 0
