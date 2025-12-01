"""Tests for the /login override blueprint."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, render_template_string
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.security import generate_password_hash

from app.routes.login_override import register_login_override
from app.routes import login_override
from app.services.password_reset_service import PendingReset


PROJECT_ROOT = Path(__file__).resolve().parents[2]
APP_TEMPLATES = PROJECT_ROOT / "app" / "templates"
CALIBRE_TEMPLATES = PROJECT_ROOT / "calibre-web" / "cps" / "templates"
APP_PACKAGE_ROOT = PROJECT_ROOT / "app"


@pytest.fixture
def flask_app(monkeypatch):
    app = Flask(__name__, template_folder=str(APP_TEMPLATES))
    app.jinja_loader = ChoiceLoader([
        FileSystemLoader(str(APP_TEMPLATES)),
        FileSystemLoader(str(APP_PACKAGE_ROOT)),
        FileSystemLoader(str(CALIBRE_TEMPLATES)),
    ])
    app.config["SECRET_KEY"] = "login-test-secret"
    register_login_override(app)
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture(autouse=True)
def stub_login_user(monkeypatch):
    monkeypatch.setattr(login_override, "login_user", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def stub_templates(monkeypatch):
    def _render(_template_name, **context):
        body = context.get("form_errors") or []
        payload = "|".join(body) if body else "OK"
        return render_template_string("{{ body }}", body=payload)

    monkeypatch.setattr(login_override, "render_template", _render)


def _stub_user(email: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=7,
        email=email,
        password=generate_password_hash("Secret123!"),
        name=email,
    )


def test_standard_login_success_sets_session(monkeypatch, client):
    monkeypatch.setattr(login_override, "_fetch_user_by_email", lambda _email: _stub_user(_email))

    resp = client.post(
        "/login",
        data={"email": "reader@example.com", "password": "Secret123!", "next": "/catalog"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/catalog")
    with client.session_transaction() as sess:
        assert sess["user_id"] == 7
        assert sess["email"] == "reader@example.com"


def test_login_with_wrong_password_shows_error(monkeypatch, client):
    monkeypatch.setattr(login_override, "_fetch_user_by_email", lambda _email: _stub_user(_email))

    resp = client.post(
        "/login",
        data={"email": "reader@example.com", "password": "bad"},
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert b"Wrong email or password" in resp.data


def test_forgot_password_triggers_email(monkeypatch, client):
    email_calls = {}

    def fake_lookup(email):
        return {"email": email, "name": "Reader"}

    monkeypatch.setattr(login_override.calibre_users_service, "lookup_user_by_email", fake_lookup)
    monkeypatch.setattr(login_override.password_reset_service, "issue_reset_token", lambda **_: "token-123")

    def record_email(**kwargs):
        email_calls.update(kwargs)
        return {"queued": True}

    monkeypatch.setattr(login_override.email_delivery, "send_password_reset_email", record_email)

    resp = client.post(
        "/login",
        data={"email": "reader@example.com", "action": "forgot"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert email_calls["recipient_email"] == "reader@example.com"
    assert "reset_url" in email_calls


def test_password_change_via_token_logs_user_in(monkeypatch, client):
    monkeypatch.setattr(
        login_override.auth_link_service,
        "decode_payload",
        lambda token: {"email": "reader@example.com", "temp_password": "Temp", "issued_at": "2024-01-01T00:00:00Z"},
    )
    monkeypatch.setattr(login_override, "_fetch_user_by_email", lambda _email: _stub_user(_email))

    pending = PendingReset(
        email="reader@example.com",
        token_type="initial",
        book_ids=[],
        temp_password="Temp",
        issued_at="2024-01-01T00:00:00Z",
    )
    monkeypatch.setattr(login_override.password_reset_service, "resolve_pending_reset", lambda **_: pending)
    monkeypatch.setattr(login_override.password_reset_service, "complete_password_change", lambda **_: {"ok": True})

    resp = client.post(
        "/login",
        data={
            "email": "reader@example.com",
            "auth": "token-xyz",
            "new_password": "NewSecret!1",
            "confirm_password": "NewSecret!1",
            "action": "complete_reset",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert sess["email"] == "reader@example.com"


def test_token_requires_password_update_before_login(monkeypatch, client):
    monkeypatch.setattr(
        login_override.auth_link_service,
        "decode_payload",
        lambda token: {"email": "reader@example.com", "temp_password": "Temp", "issued_at": "2024-01-01T00:00:00Z"},
    )
    monkeypatch.setattr(login_override, "_fetch_user_by_email", lambda _email: _stub_user(_email))

    resp = client.post(
        "/login",
        data={
            "email": "reader@example.com",
            "password": "Secret123!",
            "auth": "token-xyz",
            "action": "login",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert b"Enter and confirm your new password" in resp.data