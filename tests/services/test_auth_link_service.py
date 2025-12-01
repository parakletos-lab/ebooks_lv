"""Tests for auth_link_service encode/decode utilities."""
from __future__ import annotations

import pytest
from flask import Flask

from app.services import auth_link_service


@pytest.fixture(autouse=True)
def app_context():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    with app.app_context():
        yield


def test_round_trip_purchase_token_preserves_payload():
    token = auth_link_service.encode_payload(
        {
            "email": "Reader@example.com",
            "temp_password": "Temp123!",
            "book_ids": [5, 7],
        }
    )

    decoded = auth_link_service.decode_payload(token)

    assert decoded["email"] == "reader@example.com"
    assert decoded["temp_password"] == "Temp123!"
    assert decoded["book_ids"] == [5, 7]
    assert "issued_at" in decoded


def test_decode_rejects_tampered_token():
    token = auth_link_service.encode_payload(
        {
            "email": "reader@example.com",
            "temp_password": None,
            "book_ids": [],
        }
    )
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(auth_link_service.TokenDecodeError):
        auth_link_service.decode_payload(tampered)


def test_reset_token_expiration_enforced():
    expired_token = auth_link_service.encode_payload(
        {
            "email": "reader@example.com",
            "temp_password": None,
            "book_ids": [],
            "issued_at": "2000-01-01T00:00:00+00:00",
        }
    )

    with pytest.raises(auth_link_service.TokenExpiredError):
        auth_link_service.decode_payload(expired_token)
