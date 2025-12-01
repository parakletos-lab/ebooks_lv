"""Tests for email_templates_service subject handling."""
from __future__ import annotations

import pytest

from app.db.engine import init_engine_once, reset_for_tests
from app.services import email_templates_service


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    reset_for_tests(drop=True)
    monkeypatch.setenv("USERS_BOOKS_DB_PATH", ":memory:")
    init_engine_once()
    yield
    reset_for_tests(drop=True)


def test_save_template_persists_subject_per_language():
    email_templates_service.save_template(
        template_key="book_purchase",
        language="lv",
        html_body="<p>Body LV</p>",
        subject="Sveiki LV",
    )
    email_templates_service.save_template(
        template_key="book_purchase",
        language="en",
        html_body="<p>Body EN</p>",
        subject="Hello EN",
    )

    context = email_templates_service.fetch_templates_context()
    entries = [tmpl for tmpl in context["templates"] if tmpl["key"] == "book_purchase"]
    assert entries, "book_purchase template should be present"
    languages = entries[0]["languages"]
    assert languages["lv"]["subject"] == "Sveiki LV"
    assert languages["en"]["subject"] == "Hello EN"


def test_save_template_rejects_multiline_subject():
    with pytest.raises(email_templates_service.TemplateValidationError):
        email_templates_service.save_template(
            template_key="book_purchase",
            language="lv",
            html_body="<p>Body</p>",
            subject="Line 1\nLine 2",
        )
