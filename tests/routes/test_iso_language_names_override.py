import types
import sys

from app.routes.overrides.iso_language_names_override import register_iso_language_names_override


def test_iso_languages_override_patches_get_language_names_when_missing(monkeypatch):
    # Create a fake cps.isoLanguages module-like object.
    iso_language_names = {"en": {"fin": "Finnish", "lav": "Latvian"}}

    def original_get_language_names(locale):
        # Simulate Calibre-Web behavior for missing locale mapping.
        return None

    def original_get_language_name(locale, lang_code):
        return "Unknown"

    class _LangObj:
        def __init__(self, part1=None, part3=None):
            self.part1 = part1
            self.part3 = part3

    def get(*, name=None, part1=None, part3=None):
        # Minimal ISO639-3 -> ISO639-1 mapping for the test.
        if part3 == "fin":
            return _LangObj(part1="fi", part3="fin")
        if part3 == "lav":
            return _LangObj(part1="lv", part3="lav")
        return _LangObj(part1=None, part3=part3)

    fake_iso_languages = types.SimpleNamespace(
        _LANGUAGE_NAMES=iso_language_names,
        get_language_names=original_get_language_names,
        get_language_name=original_get_language_name,
        get=get,
    )

    fake_cps = types.SimpleNamespace(isoLanguages=fake_iso_languages)

    monkeypatch.setitem(sys.modules, "cps", fake_cps)

    app = types.SimpleNamespace()

    register_iso_language_names_override(app)

    patched = fake_iso_languages.get_language_names("lv")
    assert isinstance(patched, dict)
    assert "fin" in patched
