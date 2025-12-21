import pytest

from app.services import mozello_service


def test_upsert_product_basic_sets_text_merge_mode(monkeypatch):
    captured = {}

    class DummyResp:
        status_code = 200

        def json(self):
            return {"error": False, "ok": True}

        @property
        def text(self):
            return "{}"

    def fake_put(url, json=None, headers=None, timeout=None):
        captured["put"] = {"url": url, "json": json}
        return DummyResp()

    monkeypatch.setattr(mozello_service, "_api_headers", lambda: {"Authorization": "ApiKey test"})
    monkeypatch.setattr(mozello_service, "_throttle_wait", lambda: None)
    monkeypatch.setattr(mozello_service.requests, "put", fake_put)
    monkeypatch.setattr(mozello_service, "invalidate_cache", lambda: None)

    ok, _ = mozello_service.upsert_product_basic(
        handle="book-8",
        title="Title",
        price=10.5,
        description_html=None,
        language_code="lv",
    )
    assert ok is True
    assert captured["put"]["json"]["options"]["text_update_mode"] == "merge"


def test_upsert_product_minimal_sets_text_merge_mode(monkeypatch):
    captured = {}

    class DummyResp:
        status_code = 200

        def json(self):
            return {"error": False, "ok": True}

        @property
        def text(self):
            return "{}"

    def fake_put(url, json=None, headers=None, timeout=None):
        captured["put"] = {"url": url, "json": json}
        return DummyResp()

    monkeypatch.setattr(mozello_service, "_api_headers", lambda: {"Authorization": "ApiKey test"})
    monkeypatch.setattr(mozello_service, "_throttle_wait", lambda: None)
    monkeypatch.setattr(mozello_service.requests, "put", fake_put)
    monkeypatch.setattr(mozello_service, "invalidate_cache", lambda: None)

    ok, _ = mozello_service.upsert_product_minimal("book-8", "Title", 10.5)
    assert ok is True
    assert captured["put"]["json"]["options"]["text_update_mode"] == "merge"


def test_add_product_picture_invalidates_cache(monkeypatch):
    called = {"inv": 0}

    class DummyResp:
        status_code = 200

        def json(self):
            return {"error": False, "picture": {"uid": "uid-1"}}

        @property
        def text(self):
            return "{}"

    def fake_post(url, json=None, headers=None, timeout=None):
        return DummyResp()

    monkeypatch.setattr(mozello_service, "_api_headers", lambda: {"Authorization": "ApiKey test"})
    monkeypatch.setattr(mozello_service, "_throttle_wait", lambda: None)
    monkeypatch.setattr(mozello_service.requests, "post", fake_post)
    monkeypatch.setattr(mozello_service, "invalidate_cache", lambda: called.__setitem__("inv", called["inv"] + 1))

    ok, _ = mozello_service.add_product_picture("book-1", "Zm9v", filename="calibre-cover.jpg")
    assert ok is True
    assert called["inv"] == 1


def test_replace_tracked_cover_pictures_deletes_only_tracked(monkeypatch):
    calls = {"deleted": [], "uploaded": 0}

    def fake_list(handle):
        return True, {"error": False, "pictures": []}

    def fake_delete(handle, uid):
        calls["deleted"].append(uid)
        return True, {"error": False}

    def fake_add(handle, b64_image, filename=None):
        calls["uploaded"] += 1
        return True, {"error": False, "picture": {"uid": "uid-new"}}

    monkeypatch.setattr(mozello_service, "list_product_pictures", fake_list)
    monkeypatch.setattr(mozello_service, "delete_product_picture", fake_delete)
    monkeypatch.setattr(mozello_service, "add_product_picture", fake_add)

    ok, resp = mozello_service.replace_tracked_cover_pictures(
        "book-1",
        tracked_picture_uids=["uid-old", "  ", "uid-old-2"],
        cover_b64="Zm9v",
    )
    assert ok is True
    assert calls["deleted"] == ["uid-old", "uid-old-2"]
    assert calls["uploaded"] == 1
    assert resp["removed_uids"] == ["uid-old", "uid-old-2"]
    assert resp["uploaded_uid"] == "uid-new"


def test_replace_tracked_cover_pictures_derives_uid_when_upload_response_missing(monkeypatch):
    # Simulate Mozello upload response without uid; service should diff pictures to find the new one.
    state = {"stage": "before"}

    def fake_list(handle):
        if state["stage"] == "before":
            return True, {"error": False, "pictures": [{"uid": "uid-extra"}, {"uid": "uid-old-cover"}]}
        return True, {"error": False, "pictures": [{"uid": "uid-extra"}, {"uid": "uid-new-cover"}]}

    def fake_delete(handle, uid):
        return True, {"error": False}

    def fake_add(handle, b64_image, filename=None):
        state["stage"] = "after"
        return True, {"error": False}

    monkeypatch.setattr(mozello_service, "list_product_pictures", fake_list)
    monkeypatch.setattr(mozello_service, "delete_product_picture", fake_delete)
    monkeypatch.setattr(mozello_service, "add_product_picture", fake_add)

    ok, resp = mozello_service.replace_tracked_cover_pictures(
        "book-1",
        tracked_picture_uids=["uid-old-cover"],
        cover_b64="Zm9v",
    )
    assert ok is True
    assert resp["uploaded_uid"] == "uid-new-cover"
