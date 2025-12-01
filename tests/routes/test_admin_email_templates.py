"""Tests for /admin/ebookslv/email-templates API endpoints."""
from __future__ import annotations

import pytest  # type: ignore[import-not-found]
from flask import Flask

from app.db.engine import init_engine_once, reset_for_tests
from app.routes.admin_ebookslv import register_ebookslv_blueprint
from app.services import email_templates_service


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    reset_for_tests(drop=True)
    monkeypatch.setenv("USERS_BOOKS_DB_PATH", ":memory:")
    init_engine_once()
    yield
    reset_for_tests(drop=True)


@pytest.fixture
def admin_client(monkeypatch):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "templates-secret"
    register_ebookslv_blueprint(app)
    monkeypatch.setattr("app.routes.admin_ebookslv.ensure_admin", lambda prefer_redirect=False: True)
    with app.test_client() as client:
        yield client


def test_api_list_includes_subjects(admin_client):
    email_templates_service.save_template(
        template_key="book_purchase",
        language="lv",
        html_body="<p>Body</p>",
        subject="Sveiki",
    )

    resp = admin_client.get("/admin/ebookslv/email-templates/api/list")
    assert resp.status_code == 200
    data = resp.get_json()
    book_purchase = next(t for t in data["templates"] if t["key"] == "book_purchase")
    assert book_purchase["languages"]["lv"]["subject"] == "Sveiki"


def test_api_save_updates_subject(admin_client):
    payload = {
        "template_key": "book_purchase",
        "language": "en",
        "subject": "Hello",
        "html": "<p>Hello</p>",
    }
    resp = admin_client.post("/admin/ebookslv/email-templates/api/save", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["template"]["subject"] == "Hello"

    context = email_templates_service.fetch_templates_context()
    book_purchase = next(t for t in context["templates"] if t["key"] == "book_purchase")
    assert book_purchase["languages"]["en"]["subject"] == "Hello"
