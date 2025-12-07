"""Tests for email_delivery service."""
from __future__ import annotations

from typing import List

import pytest  # type: ignore[import-not-found]
from flask import Flask

from app.db.engine import init_engine_once, reset_for_tests
from app.services import email_delivery, email_templates_service


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
    app.config["SECRET_KEY"] = "email-secret"
    with app.test_request_context("/", base_url="https://ebooks.test/"):
        yield


def _seed_template():
    email_templates_service.save_template(
        template_key="book_purchase",
        language="lv",
        subject="Hello {{user_name}}",
        html_body="<p>Hi {{user_name}}</p><ul>{{books}}</ul><a href='{{my_books}}'>My books</a>",
    )


def _seed_reset_template():
    email_templates_service.save_template(
        template_key="password_reset",
        language="lv",
        subject="Reset access for {{user_name}}",
        html_body="<p>Use this link: <a href='{{new_password_url}}'>Reset</a></p>",
    )


def _install_email_dependencies(monkeypatch):
    class DummyConfig:
        def get_mail_server_configured(self):
            return True

        def get_mail_settings(self):
            return {
                "mail_server_type": 0,
                "mail_server": "smtp.test",
                "mail_port": 25,
                "mail_use_ssl": 0,
                "mail_login": "",
                "mail_password_e": "",
                "mail_from": "ebooks@test",
            }

    class FakeWorker:
        added: List[dict] = []

        @classmethod
        def add(cls, user, task, hidden=False):  # pragma: no cover - simple recorder
            cls.added.append({"user": user, "task": task, "hidden": hidden})

    class FakeHtmlTaskEmail:
        def __init__(
            self,
            *,
            html_body: str,
            subject: str,
            settings: dict,
            recipient: str,
            text_body: str,
            task_message: str,
        ):
            self._html_body = html_body
            self.subject = subject
            self.settings = settings
            self.recipient = recipient
            self.text = text_body
            self.task_message = task_message

    monkeypatch.setattr(email_delivery, "cw_config", DummyConfig())
    monkeypatch.setattr(email_delivery, "WorkerThread", FakeWorker)
    monkeypatch.setattr(email_delivery, "HtmlTaskEmail", FakeHtmlTaskEmail)

    return FakeWorker


def test_send_purchase_email_renders_tokens_and_queues_task(monkeypatch, request_context):
    _seed_template()
    worker = _install_email_dependencies(monkeypatch)

    result = email_delivery.send_book_purchase_email(
        recipient_email="reader@example.com",
        user_name="Reader",
        books=[
            email_delivery.BookDeliveryItem(book_id=101, title="Alpha", language_code="lv"),
            email_delivery.BookDeliveryItem(book_id=202, title="Beta", language_code="lv"),
        ],
        shop_url="https://shop.example.com",
        my_books_url=None,
        auth_token="test-token",
    )

    assert result["queued"] is True
    assert result["language"] == "lv"
    assert len(worker.added) == 1
    task = worker.added[0]["task"]
    assert task.subject == "Hello Reader"
    assert "test-token" in task._html_body  # type: ignore[attr-defined]
    assert "https://ebooks.test/login?next=%2Fbook%2F101&auth=test-token" in task.text
    assert "https://ebooks.test/login?next=%2Fcatalog%2Fmy-books&auth=test-token" in task._html_body  # type: ignore[attr-defined]


def test_send_purchase_email_plain_my_books_link_without_auth_token(monkeypatch, request_context):
    _seed_template()
    worker = _install_email_dependencies(monkeypatch)

    email_delivery.send_book_purchase_email(
        recipient_email="reader@example.com",
        user_name="Reader",
        books=[
            email_delivery.BookDeliveryItem(book_id=101, title="Alpha", language_code="lv"),
        ],
        shop_url="https://shop.example.com",
        my_books_url=None,
        auth_token=None,
    )

    assert len(worker.added) == 1
    task = worker.added[0]["task"]
    assert "https://ebooks.test/catalog/my-books" in task._html_body  # type: ignore[attr-defined]
    assert "login?next=%2Fcatalog%2Fmy-books" not in task._html_body  # type: ignore[attr-defined]


def test_send_purchase_email_requires_mail_settings(monkeypatch, request_context):
    _seed_template()

    class DummyConfig:
        def get_mail_server_configured(self):
            return False

    monkeypatch.setattr(email_delivery, "cw_config", DummyConfig())

    with pytest.raises(email_delivery.MailNotConfiguredError):
        email_delivery.send_book_purchase_email(
            recipient_email="reader@example.com",
            user_name="Reader",
            books=[email_delivery.BookDeliveryItem(book_id=1, title="Only", language_code="lv")],
            shop_url="https://shop.example.com",
        )


def test_send_password_reset_email_queues_task(monkeypatch, request_context):
    _seed_reset_template()

    class DummyConfig:
        def get_mail_server_configured(self):
            return True

        def get_mail_settings(self):
            return {
                "mail_server_type": 0,
                "mail_server": "smtp.test",
                "mail_port": 25,
                "mail_use_ssl": 0,
                "mail_login": "",
                "mail_password_e": "",
                "mail_from": "ebooks@test",
            }

    class FakeWorker:
        added: List[dict] = []

        @classmethod
        def add(cls, user, task, hidden=False):  # pragma: no cover - recorder
            cls.added.append({"user": user, "task": task, "hidden": hidden})

    class FakeHtmlTaskEmail:
        def __init__(
            self,
            *,
            html_body: str,
            subject: str,
            settings: dict,
            recipient: str,
            text_body: str,
            task_message: str,
        ):
            self.html_body = html_body
            self.subject = subject
            self.settings = settings
            self.recipient = recipient
            self.text_body = text_body
            self.task_message = task_message

    monkeypatch.setattr(email_delivery, "cw_config", DummyConfig())
    monkeypatch.setattr(email_delivery, "WorkerThread", FakeWorker)
    monkeypatch.setattr(email_delivery, "HtmlTaskEmail", FakeHtmlTaskEmail)

    reset_url = "https://ebooks.test/login?auth=token"
    result = email_delivery.send_password_reset_email(
        recipient_email="reader@example.com",
        user_name="Reader",
        reset_url=reset_url,
        preferred_language="lv",
    )

    assert result["queued"] is True
    assert len(FakeWorker.added) == 1
    task = FakeWorker.added[0]["task"]
    assert task.recipient == "reader@example.com"
    assert reset_url in task.html_body
    assert reset_url in task.text_body
