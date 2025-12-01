"""Tests for password_reset_service helpers."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from app.services import auth_link_service, password_reset_service


@pytest.fixture(autouse=True)
def app_context():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "password-reset-secret"
    with app.app_context():
        yield


def test_issue_initial_token_hashes_and_returns_token(monkeypatch):
    calls: dict = {}

    def fake_upsert_token(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        password_reset_service.reset_passwords_repo,
        "upsert_token",
        fake_upsert_token,
    )

    token = password_reset_service.issue_initial_token(
        email="Reader@example.com",
        temp_password="Temp123!",
        book_ids=[11, 42],
    )

    assert calls["email"] == "reader@example.com"
    assert calls["token_type"] == "initial"
    assert calls["password_hash"] != "Temp123!"

    decoded = auth_link_service.decode_payload(token)
    assert decoded["email"] == "reader@example.com"
    assert decoded["temp_password"] == "Temp123!"
    assert decoded["book_ids"] == [11, 42]


def test_issue_reset_token_requires_existing_user(monkeypatch):
    monkeypatch.setattr(
        password_reset_service.calibre_users_service,
        "lookup_user_by_email",
        lambda _email: None,
    )

    with pytest.raises(password_reset_service.PendingResetNotFoundError):
        password_reset_service.issue_reset_token(email="missing@example.com")


def test_issue_reset_token_generates_expiring_link(monkeypatch):
    monkeypatch.setattr(
        password_reset_service.calibre_users_service,
        "lookup_user_by_email",
        lambda _email: {"id": 99},
    )
    recorded: dict = {}

    def fake_upsert_token(**kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        password_reset_service.reset_passwords_repo,
        "upsert_token",
        fake_upsert_token,
    )

    token = password_reset_service.issue_reset_token(email="reader@example.com", book_ids=[3])

    assert recorded["token_type"] == "reset"
    decoded = auth_link_service.decode_payload(token)
    assert decoded["temp_password"] is None
    assert decoded["book_ids"] == [3]


def test_resolve_pending_reset_initial_flow(monkeypatch):
    hashed = generate_password_hash("Temp123!")

    def fake_get_token(**kwargs):
        assert kwargs["email"] == "reader@example.com"
        assert kwargs["token_type"] == "initial"
        return SimpleNamespace(password_hash=hashed)

    monkeypatch.setattr(
        password_reset_service.reset_passwords_repo,
        "get_token",
        fake_get_token,
    )

    token = auth_link_service.encode_payload(
        {
            "email": "Reader@example.com",
            "temp_password": "Temp123!",
            "book_ids": [5],
        }
    )

    pending = password_reset_service.resolve_pending_reset(email="reader@example.com", token=token)

    assert pending.token_type == "initial"
    assert pending.book_ids == [5]
    assert pending.temp_password == "Temp123!"


def test_resolve_pending_reset_requires_repo_record(monkeypatch):
    monkeypatch.setattr(
        password_reset_service.reset_passwords_repo,
        "get_token",
        lambda **_kwargs: None,
    )
    token = auth_link_service.encode_payload(
        {
            "email": "reader@example.com",
            "temp_password": None,
            "book_ids": [],
        }
    )

    with pytest.raises(password_reset_service.PendingResetNotFoundError):
        password_reset_service.resolve_pending_reset(email="reader@example.com", token=token)


def test_complete_password_change_updates_user_and_clears_tokens(monkeypatch):
    lookup_calls: dict = {}

    def fake_lookup(email):
        lookup_calls.setdefault("emails", []).append(email)
        return {"id": 7, "email": email}

    def fake_update(user_id, new_password):
        return {"id": user_id, "email": "reader@example.com", "name": "reader"}

    deleted: list = []

    def fake_delete(**kwargs):
        deleted.append(kwargs["token_type"])
        return True

    monkeypatch.setattr(password_reset_service.calibre_users_service, "lookup_user_by_email", fake_lookup)
    monkeypatch.setattr(password_reset_service.calibre_users_service, "update_user_password", fake_update)
    monkeypatch.setattr(password_reset_service.reset_passwords_repo, "delete_token", fake_delete)

    result = password_reset_service.complete_password_change(
        email="Reader@example.com", new_password="NewPassword!"
    )

    assert result["id"] == 7
    assert lookup_calls["emails"] == ["reader@example.com"]
    assert deleted == ["initial", "reset"]


def test_purge_expired_records_passthrough(monkeypatch):
    monkeypatch.setattr(
        password_reset_service.reset_passwords_repo,
        "purge_expired_tokens",
        lambda older_than_days: older_than_days,
    )

    assert password_reset_service.purge_expired_records(older_than_days=10) == 10
