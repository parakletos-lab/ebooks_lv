"""Integration tests for orders_service.process_webhook_order."""
from __future__ import annotations

from typing import Dict, List, Optional

import pytest  # type: ignore[import-not-found]
from flask import Flask

from app.db.engine import init_engine_once, reset_for_tests
from app.db.repositories import reset_passwords_repo, users_books_repo
from app.services import orders_service, password_reset_service


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    reset_for_tests(drop=True)
    monkeypatch.setenv("USERS_BOOKS_DB_PATH", ":memory:")
    init_engine_once()
    yield
    reset_for_tests(drop=True)


@pytest.fixture
def request_context():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "orders-secret"
    with app.test_request_context("/mozello/webhook", base_url="https://ebooks.test/"):
        yield


def test_process_webhook_order_triggers_token_and_email(monkeypatch, request_context):
    email_address = "customer@example.com"

    def fake_lookup_books(handles_iterable):
        mapping: Dict[str, Dict[str, object]] = {}
        for idx, handle in enumerate(handles_iterable, start=1):
            key = handle.strip().lower()
            mapping[key] = {
                "book_id": 100 + idx,
                "title": handle.title(),
                "language_code": "lv",
            }
        return mapping

    monkeypatch.setattr(orders_service.books_sync, "lookup_books_by_handles", fake_lookup_books)
    monkeypatch.setattr(orders_service.mozello_service, "get_store_url", lambda *_a, **_k: "https://shop.example.com")

    existing_user: Optional[Dict[str, object]] = None

    def fake_lookup_user(_email: str):
        return existing_user

    def fake_create_user(order_id: int, **kwargs):
        nonlocal existing_user
        assert kwargs.get("preferred_username") == "Customer Example"
        assert kwargs.get("preferred_language") == "lv"
        existing_user = {
            "id": 77,
            "email": email_address,
            "name": "reader@example.com",
            "locale": "lv",
        }
        users_books_repo.update_links(order_id, calibre_user_id=existing_user["id"])
        return {"status": "created", "user": existing_user, "password": "Temp123!Pass"}

    monkeypatch.setattr(orders_service, "lookup_user_by_email", fake_lookup_user)
    monkeypatch.setattr(orders_service, "create_user_for_order", fake_create_user)

    wishlist_calls: List[Dict[str, object]] = []

    def fake_ensure_wishlist(user_id: int, *, user_locale=None):
        wishlist_calls.append({"user_id": user_id, "user_locale": user_locale})
        return {"status": "created", "shelf_id": 1, "name": "Vēlmju saraksts"}

    monkeypatch.setattr(orders_service.shelves_service, "ensure_wishlist_shelf_for_user", fake_ensure_wishlist)

    email_calls: List[Dict[str, object]] = []

    def fake_send_purchase_email(**kwargs):
        email_calls.append(kwargs)
        return {"language": "lv", "book_count": len(kwargs.get("books", [])), "queued": True}

    monkeypatch.setattr(orders_service.email_delivery, "send_book_purchase_email", fake_send_purchase_email)

    issued_token: Dict[str, str] = {}
    real_issue_initial_token = password_reset_service.issue_initial_token

    def recording_issue_initial_token(**kwargs):
        token = real_issue_initial_token(**kwargs)
        issued_token["value"] = token
        return token

    monkeypatch.setattr(orders_service.password_reset_service, "issue_initial_token", recording_issue_initial_token)

    payload = {
        "payment_status": "paid",
        "email": email_address,
        "order_id": "moz-001",
        "name": "Customer Example",
        "cart": [
            {"product_handle": "alpha"},
            {"product_handle": "beta"},
        ],
    }

    result = orders_service.process_webhook_order(payload)
    summary = result["summary"]

    assert summary["orders_created"] == 2
    assert summary["user_created"] == 1
    assert summary["books_included"] == 2
    assert summary["email_queued"] is True
    assert summary["initial_token_issued"] is True

    assert wishlist_calls == [{"user_id": 77, "user_locale": "lv"}]

    assert len(email_calls) == 1
    call = email_calls[0]
    assert call["recipient_email"] == email_address
    assert len(call["books"]) == 2
    assert call["auth_token"] == issued_token["value"]
    assert call["preferred_language"] == "lv"

    token_record = reset_passwords_repo.get_token(email=email_address, token_type="initial")
    assert token_record is not None


def test_process_webhook_order_prefers_origin_url_language(monkeypatch, request_context):
    email_address = "customer@example.com"

    def fake_lookup_books(handles_iterable):
        mapping: Dict[str, Dict[str, object]] = {}
        for idx, handle in enumerate(handles_iterable, start=1):
            key = handle.strip().lower()
            mapping[key] = {
                "book_id": 200 + idx,
                "title": handle.title(),
                "language_code": "lv",  # would be used only as fallback
            }
        return mapping

    monkeypatch.setattr(orders_service.books_sync, "lookup_books_by_handles", fake_lookup_books)

    monkeypatch.setattr(orders_service.mozello_service, "infer_language_from_origin_url", lambda *_a, **_k: "ru")

    def fake_get_store_url(lang=None):
        if lang == "ru":
            return "https://www.e-books.lv/magazin"
        if lang == "lv":
            return "https://www.e-books.lv/veikals"
        if lang == "en":
            return "https://www.e-books.lv/shop"
        return "https://www.e-books.lv/shop"

    monkeypatch.setattr(orders_service.mozello_service, "get_store_url", fake_get_store_url)

    existing_user: Optional[Dict[str, object]] = None

    def fake_lookup_user(_email: str):
        return existing_user

    def fake_create_user(order_id: int, **kwargs):
        nonlocal existing_user
        # The key assertion for this test: language comes from origin_url (ru), not book language.
        assert kwargs.get("preferred_language") == "ru"
        existing_user = {
            "id": 88,
            "email": email_address,
            "name": "reader@example.com",
            "locale": "ru",
        }
        users_books_repo.update_links(order_id, calibre_user_id=existing_user["id"])
        return {"status": "created", "user": existing_user, "password": "Temp123!Pass"}

    monkeypatch.setattr(orders_service, "lookup_user_by_email", fake_lookup_user)
    monkeypatch.setattr(orders_service, "create_user_for_order", fake_create_user)
    monkeypatch.setattr(orders_service.shelves_service, "ensure_wishlist_shelf_for_user", lambda *_a, **_k: {"status": "created"})

    email_calls: List[Dict[str, object]] = []

    def fake_send_purchase_email(**kwargs):
        email_calls.append(kwargs)
        return {"language": "ru", "book_count": len(kwargs.get("books", [])), "queued": True}

    monkeypatch.setattr(orders_service.email_delivery, "send_book_purchase_email", fake_send_purchase_email)

    payload = {
        "payment_status": "paid",
        "email": email_address,
        "order_id": "moz-ru-001",
        "name": "Customer Example",
        "origin_url": "https://www.e-books.lv/magazin/",  # trailing slash should still match
        "cart": [
            {"product_handle": "alpha"},
            {"product_handle": "beta"},
        ],
    }

    result = orders_service.process_webhook_order(payload)
    summary = result["summary"]
    assert summary["user_created"] == 1
    assert summary["email_queued"] is True

    assert len(email_calls) == 1
    call = email_calls[0]
    assert call["preferred_language"] == "ru"
    assert call["shop_url"].rstrip("/") == "https://www.e-books.lv/magazin"


def test_process_webhook_order_email_language_prefers_order_hint(monkeypatch, request_context):
    email_address = "customer@example.com"

    def fake_lookup_books(handles_iterable):
        return {
            "alpha": {"book_id": 301, "title": "Alpha", "language_code": "lv"},
        }

    monkeypatch.setattr(orders_service.books_sync, "lookup_books_by_handles", fake_lookup_books)
    monkeypatch.setattr(orders_service.mozello_service, "infer_language_from_origin_url", lambda *_a, **_k: "ru")
    monkeypatch.setattr(orders_service.mozello_service, "get_store_url", lambda *_a, **_k: "https://shop.example.com")

    # User exists with locale=en, but order hint says ru → email should be ru.
    monkeypatch.setattr(
        orders_service,
        "lookup_user_by_email",
        lambda _email: {"id": 55, "email": email_address, "name": email_address, "locale": "en"},
    )
    monkeypatch.setattr(orders_service, "update_user_display_name", lambda *_a, **_k: {"ok": True})

    email_calls: List[Dict[str, object]] = []

    def fake_send_purchase_email(**kwargs):
        email_calls.append(kwargs)
        return {"language": kwargs.get("preferred_language"), "queued": True}

    monkeypatch.setattr(orders_service.email_delivery, "send_book_purchase_email", fake_send_purchase_email)

    payload = {
        "payment_status": "paid",
        "email": email_address,
        "order_id": "moz-ru-002",
        "name": "Druid",
        "origin_url": "https://www.e-books.lv/magazin/",
        "cart": [{"product_handle": "alpha"}],
    }

    result = orders_service.process_webhook_order(payload)
    assert result["summary"]["email_queued"] is True
    assert len(email_calls) == 1
    assert email_calls[0]["preferred_language"] == "ru"