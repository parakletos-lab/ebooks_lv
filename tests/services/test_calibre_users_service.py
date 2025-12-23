"""Tests for calibre_users_service.update_user_password helper."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from werkzeug.security import check_password_hash

import app.services.calibre_users_service as calibre_users_service


class FakeUser:
    def __init__(self, user_id: int, email: str, name: str | None = None):
        self.id = user_id
        self.email = email
        self.name = name or email
        self.password = "old"


class FakeQuery:
    def __init__(self, user: FakeUser | None):
        self._user = user

    def filter(self, *args, **kwargs):  # pragma: no cover - passthrough
        return self

    def one_or_none(self):
        return self._user


class FakeSession:
    def __init__(self, user: FakeUser | None):
        self._user = user
        self.commits = 0
        self.rolled_back = False

    def query(self, *_args, **_kwargs):
        return FakeQuery(self._user)

    def commit(self):
        self.commits += 1

    def rollback(self):  # pragma: no cover - defensive guard
        self.rolled_back = True


class RecordingHelper:
    def __init__(self, *, should_raise: bool = False):
        self.should_raise = should_raise
        self.validated_values: list[str] = []

    def valid_password(self, value: str):
        self.validated_values.append(value)
        if self.should_raise:
            raise ValueError("invalid_password")


class _ComparableId:
    def __eq__(self, _other):  # pragma: no cover - trivial helper
        return True


class FakeUserModel:
    id = _ComparableId()


def _configure_runtime(monkeypatch, user: FakeUser | None, helper: RecordingHelper):
    session = FakeSession(user)
    ub_stub = SimpleNamespace(session=session, User=FakeUserModel)
    monkeypatch.setattr(calibre_users_service, "ub", ub_stub, raising=False)
    monkeypatch.setattr(calibre_users_service, "helper", helper, raising=False)
    return session


def test_update_user_password_hashes_and_commits(monkeypatch):
    user = FakeUser(1, "reader@example.com")
    helper = RecordingHelper()
    session = _configure_runtime(monkeypatch, user, helper)

    result = calibre_users_service.update_user_password(user.id, "NewSecure123!")

    assert result == {"id": 1, "email": "reader@example.com", "name": "reader@example.com"}
    assert helper.validated_values == ["NewSecure123!"]
    assert session.commits == 1
    assert check_password_hash(user.password, "NewSecure123!") is True


def test_update_user_password_propagates_validation_errors(monkeypatch):
    user = FakeUser(2, "other@example.com")
    helper = RecordingHelper(should_raise=True)
    session = _configure_runtime(monkeypatch, user, helper)

    with pytest.raises(ValueError):
        calibre_users_service.update_user_password(user.id, "short")

    assert session.commits == 0
    assert helper.validated_values == ["short"]
    assert user.password == "old"


def test_update_user_password_missing_user(monkeypatch):
    helper = RecordingHelper()
    session = _configure_runtime(monkeypatch, None, helper)

    with pytest.raises(calibre_users_service.UserNotFoundError):
        calibre_users_service.update_user_password(999, "NewSecure123!")

    assert session.commits == 0


def test_apply_language_preference_accepts_latvian_variants():
    user = SimpleNamespace(locale=None, default_language=None)
    normalized = calibre_users_service._apply_language_preference(user, "lav")

    assert normalized == "lv"
    assert user.locale == "lv"
    assert user.default_language == "all"

    user_two = SimpleNamespace(locale=None, default_language=None)
    normalized_two = calibre_users_service._apply_language_preference(user_two, "LV-lv")

    assert normalized_two == "lv"
    assert user_two.locale == "lv"
    assert user_two.default_language == "all"


def test_normalize_language_preference_handles_unknown():
    assert calibre_users_service._normalize_language_preference(None) is None
    assert calibre_users_service._normalize_language_preference("   ") is None
    assert calibre_users_service._normalize_language_preference("de") is None
