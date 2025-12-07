"""Locale selection and language switch behavior tests."""
from __future__ import annotations

import pytest
from flask import Flask, jsonify

from app.routes.language_switch import register_language_switch
from app.routes.login_override import register_login_override
from app.routes.overrides import locale_override
from app.routes.overrides.locale_override import SESSION_LOCALE_KEY


@pytest.fixture(autouse=True)
def stub_default_locale_sources(monkeypatch):
    # Default Calibre locale would be EN; stub so we can assert LV override for anonymous users.
    monkeypatch.setattr(locale_override, "_cw_get_locale", lambda: "en")
    monkeypatch.setattr(locale_override, "get_current_user_id", lambda: None)


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "locale-test-secret"
    register_language_switch(app)
    register_login_override(app)

    @app.route("/", endpoint="web.index")
    def home():
        return "OK"

    @app.route("/locale")
    def show_locale():
        return jsonify({"locale": locale_override._select_locale()})

    return app


def test_anonymous_first_visit_defaults_to_lv_sets_session(flask_app):
    client = flask_app.test_client()

    resp = client.get("/locale")

    assert resp.get_json()["locale"] == "lv"
    with client.session_transaction() as sess:
        assert sess[SESSION_LOCALE_KEY] == "lv"


def test_session_locale_respected(flask_app):
    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess[SESSION_LOCALE_KEY] = "ru"

    resp = client.get("/locale")

    assert resp.get_json()["locale"] == "ru"


def test_logged_in_uses_calibre_locale(monkeypatch, flask_app):
    monkeypatch.setattr(locale_override, "get_current_user_id", lambda: 42)
    monkeypatch.setattr(locale_override, "_cw_get_locale", lambda: "en")
    client = flask_app.test_client()

    resp = client.get("/locale")

    assert resp.get_json()["locale"] == "en"
    with client.session_transaction() as sess:
        assert SESSION_LOCALE_KEY not in sess


def test_language_switch_scoped_per_client(flask_app):
    client_one = flask_app.test_client()
    client_two = flask_app.test_client()

    resp = client_one.post("/language/switch", json={"language": "ru"})
    assert resp.status_code == 200
    with client_one.session_transaction() as sess:
        assert sess[SESSION_LOCALE_KEY] == "ru"

    resp_two = client_two.get("/locale")

    assert resp_two.get_json()["locale"] == "lv"
    with client_two.session_transaction() as sess:
        assert sess[SESSION_LOCALE_KEY] == "lv"


def test_register_locale_override_without_localeselector(monkeypatch):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "fallback-test"

    class FakeBabel:
        def __init__(self):
            self.locale_selector = None

        def init_app(self, _app, locale_selector=None):
            self.locale_selector = locale_selector

    fake_babel = FakeBabel()
    monkeypatch.setattr(locale_override, "babel", fake_babel)
    monkeypatch.setattr(app, "_users_books_locale_override", False, raising=False)

    locale_override.register_locale_override(app)

    assert getattr(app, "_users_books_locale_override", False) is True
    assert fake_babel.locale_selector is locale_override._select_locale


def test_login_sets_user_locale_in_session(monkeypatch, flask_app):
    client = flask_app.test_client()

    class StubUser:
        def __init__(self):
            self.id = 9
            self.locale = "en"

    # Patch login_user to no-op and calibre user lookup
    monkeypatch.setattr(locale_override, "get_current_user_id", lambda: None)
    monkeypatch.setattr("app.routes.login_override.login_user", lambda *_, **__: None)
    monkeypatch.setattr("app.routes.login_override._authenticate_credentials", lambda email, password: StubUser())
    monkeypatch.setattr("app.routes.login_override._fetch_user_by_email", lambda _email: StubUser())
    monkeypatch.setattr("app.routes.login_override._", lambda msg, **kwargs: msg)

    resp = client.post("/login", data={"email": "reader@example.com", "password": "secret", "action": "login"})
    assert resp.status_code in (302, 303)

    with client.session_transaction() as sess:
        assert sess[SESSION_LOCALE_KEY] == "en"
