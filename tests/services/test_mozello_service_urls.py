import pytest

from app.services import mozello_service


def test_normalize_product_language_accepts_locales():
    assert mozello_service._normalize_product_language("ru_RU") == "ru"
    assert mozello_service._normalize_product_language("ru-RU") == "ru"
    assert mozello_service._normalize_product_language("lv_LV") == "lv"
    assert mozello_service._normalize_product_language("lv-LV") == "lv"
    assert mozello_service._normalize_product_language("en_US") == "en"


@pytest.mark.parametrize(
    "base,path,expected",
    [
        ("https://ebooks.lv", "/store/item/book/", "https://ebooks.lv/store/item/book/"),
        ("https://ebooks.lv/en", "/store/item/book/", "https://ebooks.lv/en/store/item/book/"),
        ("https://ebooks.lv/en", "/en/store/item/book/", "https://ebooks.lv/en/store/item/book/"),
        ("https://ebooks.lv/en/", "en/store/item/book/", "https://ebooks.lv/en/store/item/book/"),
    ],
)
def test_join_store_base_and_path_no_double_prefix(base, path, expected):
    assert mozello_service._join_store_base_and_path(base, path) == expected


def test_derive_relative_url_prefers_full_url_language():
    payload = {
        "error": False,
        "product": {
            "handle": "uid-test",
            "full_url": {
                "lv": "https://ebooks.lv/store/item/lv-slug/",
                "ru": "https://ebooks.lv/ru/store/item/ru-slug/",
                "en": "https://ebooks.lv/en/store/item/en-slug/",
            },
            "url": {"lv": "lv-slug", "ru": "ru-slug", "en": "en-slug"},
            "category_handle": "books",
        },
    }

    assert mozello_service.derive_relative_url_from_product(payload, preferred_language="lv") == "https://ebooks.lv/store/item/lv-slug/"
    assert mozello_service.derive_relative_url_from_product(payload, preferred_language="ru") == "https://ebooks.lv/ru/store/item/ru-slug/"
    assert mozello_service.derive_relative_url_from_product(payload, preferred_language="en") == "https://ebooks.lv/en/store/item/en-slug/"


def test_resolve_product_storefront_url_joins_full_url_with_store_base(monkeypatch):
    monkeypatch.setattr(mozello_service, "fetch_product", lambda handle: (True, {
        "error": False,
        "full_url": {"lv": "/item/book-8/"},
        "handle": handle,
    }))
    monkeypatch.setattr(mozello_service, "get_store_url", lambda language_code=None: "https://www.e-books.lv/veikals")

    url = mozello_service.resolve_product_storefront_url("book-8", "lv")
    assert url == "https://www.e-books.lv/veikals/item/book-8/"


def test_upsert_product_basic_sets_url_for_all_languages(monkeypatch):
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

    ok, _ = mozello_service.upsert_product_basic(
        handle="book-8",
        title="Title",
        price=10.5,
        description_html=None,
        language_code="lv",
    )
    assert ok is True
    url_field = captured["put"]["json"]["product"]["url"]
    assert url_field == {"lv": "book-8", "ru": "book-8", "en": "book-8"}


def test_upsert_product_minimal_sets_url_for_all_languages(monkeypatch):
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

    ok, _ = mozello_service.upsert_product_minimal("book-8", "Title", 10.5)
    assert ok is True
    url_field = captured["put"]["json"]["product"]["url"]
    assert url_field == {"lv": "book-8", "ru": "book-8", "en": "book-8"}
