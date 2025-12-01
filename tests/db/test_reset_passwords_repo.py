"""Tests for reset_passwords_repo helpers using in-memory SQLite."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.db import plugin_session
from app.db.engine import init_engine_once, reset_for_tests
from app.db.models import ResetPasswordToken
from app.db.repositories import reset_passwords_repo


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    reset_for_tests(drop=True)
    monkeypatch.setenv("USERS_BOOKS_DB_PATH", ":memory:")
    init_engine_once()
    yield
    reset_for_tests(drop=True)


def _count_tokens() -> int:
    with plugin_session() as session:
        return session.query(ResetPasswordToken).count()


def test_upsert_and_fetch_token_updates_existing_record():
    first = reset_passwords_repo.upsert_token(
        email="reader@example.com",
        token_type="initial",
        password_hash="hash-1",
    )
    assert first.password_hash == "hash-1"

    second = reset_passwords_repo.upsert_token(
        email="reader@example.com",
        token_type="initial",
        password_hash="hash-2",
    )
    assert second.id == first.id
    assert second.password_hash == "hash-2"

    fetched = reset_passwords_repo.get_token(email="reader@example.com", token_type="initial")
    assert fetched is not None
    assert fetched.id == first.id
    assert _count_tokens() == 1


def test_delete_token_returns_boolean_result():
    reset_passwords_repo.upsert_token(
        email="reader@example.com",
        token_type="reset",
        password_hash=None,
    )
    assert _count_tokens() == 1

    removed = reset_passwords_repo.delete_token(email="reader@example.com", token_type="reset")
    assert removed is True
    assert _count_tokens() == 0

    removed_again = reset_passwords_repo.delete_token(email="reader@example.com", token_type="reset")
    assert removed_again is False


def test_purge_expired_tokens_removes_old_rows():
    reset_passwords_repo.upsert_token(
        email="old@example.com",
        token_type="reset",
        password_hash=None,
    )
    reset_passwords_repo.upsert_token(
        email="fresh@example.com",
        token_type="reset",
        password_hash=None,
    )
    cutoff = datetime.utcnow() - timedelta(days=31)
    with plugin_session() as session:
        old_token = (
            session.query(ResetPasswordToken)
            .filter(ResetPasswordToken.email == "old@example.com")
            .one()
        )
        old_token.created_at = cutoff

    deleted = reset_passwords_repo.purge_expired_tokens()
    assert deleted == 1
    remaining = reset_passwords_repo.get_token(email="fresh@example.com", token_type="reset")
    assert remaining is not None
    missing = reset_passwords_repo.get_token(email="old@example.com", token_type="reset")
    assert missing is None
