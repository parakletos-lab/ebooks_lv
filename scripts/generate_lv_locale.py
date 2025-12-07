#!/usr/bin/env python3
"""Generate Latvian Calibre-Web translations from upstream templates."""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path
from typing import Dict, List

import polib
from argostranslate import translate

PLACEHOLDER_RE = re.compile(
    r"(%%|%\([^)]+\)[#0\- +]?\d*(?:\.\d+)?[A-Za-z]|%[#0\- +]?\d*(?:\.\d+)?[A-Za-z]|\{[^{}]+\}|\{\}|\\n|\\r|\\t|https?://\S+|&[A-Za-z0-9#]+;|\S+@\S+)"
)
TOKEN_TEMPLATE = "[[PH{index}]]"


def build_translator():
    languages = translate.get_installed_languages()
    try:
        src_lang = next(lang for lang in languages if lang.code == "en")
        dst_lang = next(lang for lang in languages if lang.code == "lv")
    except StopIteration as exc:  # pragma: no cover - defensive
        raise SystemExit("Missing Argos translation packages for en->lv") from exc
    return src_lang.get_translation(dst_lang)


def has_letters(text: str) -> bool:
    return any(char.isalpha() for char in text)


def protect_tokens(text: str) -> tuple[str, List[str]]:
    tokens: List[str] = []

    def _replace(match: re.Match[str]) -> str:
        token = TOKEN_TEMPLATE.format(index=len(tokens))
        tokens.append(match.group(0))
        return token

    return PLACEHOLDER_RE.sub(_replace, text), tokens


def restore_tokens(text: str, tokens: List[str]) -> str:
    for index, value in enumerate(tokens):
        text = text.replace(TOKEN_TEMPLATE.format(index=index), value)
    return text


def translate_text(translator, text: str, cache: Dict[str, str]) -> str:
    if not text or not has_letters(text):
        return text
    cached = cache.get(text)
    if cached is not None:
        return cached
    translated_lines: List[str] = []
    for line in text.split("\n"):
        protected, tokens = protect_tokens(line)
        if not has_letters(protected):
            translated_lines.append(restore_tokens(protected, tokens))
            continue
        translated = translator.translate(protected)
        translated_lines.append(restore_tokens(translated, tokens))
    result = "\n".join(translated_lines)
    cache[text] = result
    return result


def update_metadata(po: polib.POFile) -> None:
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M+0000")
    po.metadata["PO-Revision-Date"] = now
    po.metadata["Last-Translator"] = "ebooks.lv <support@ebooks.lv>"
    po.metadata["Language"] = "lv"
    po.metadata["Language-Team"] = "ebooks.lv"
    po.metadata.setdefault(
        "Plural-Forms",
        "nplurals=3; plural=(n % 10 == 1 && n % 100 != 11 ? 0 : n % 10 >= 2 && n % 10 <= 9 && (n % 100 < 11 || n % 100 > 19) ? 1 : 2);",
    )


def translate_po(source: Path, destination: Path) -> None:
    translator = build_translator()
    po = polib.pofile(str(source))
    cache: Dict[str, str] = {}

    for entry in po:
        if entry.obsolete:
            continue
        if not entry.msgid:
            continue
        entry.flags = [flag for flag in entry.flags if flag != "fuzzy"]
        if entry.msgid_plural:
            singular = translate_text(translator, entry.msgid, cache)
            plural = translate_text(translator, entry.msgid_plural, cache)
            entry.msgstr_plural[0] = singular
            entry.msgstr_plural[1] = plural
            entry.msgstr_plural[2] = plural
        else:
            entry.msgstr = translate_text(translator, entry.msgid, cache)
    update_metadata(po)
    destination.parent.mkdir(parents=True, exist_ok=True)
    po.save(str(destination))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("calibre-web/cps/translations/ru/LC_MESSAGES/messages.po"),
        help="Path to upstream template .po file",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("translations/calibre-web/lv/LC_MESSAGES/messages.po"),
        help="Path to write the Latvian translation",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Source file {args.source} not found", file=sys.stderr)
        sys.exit(1)

    translate_po(args.source, args.destination)


if __name__ == "__main__":
    main()
