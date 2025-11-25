"""Email template management service."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from app.db.repositories import email_templates_repo


LANGUAGES = ("lv", "ru", "en")
TEMPLATE_DEFINITIONS = {
    "book_purchase": {
        "label": "Book purchase e-mail",
        "description": "Sent after successful Mozello purchase to share download details.",
    }
}
TOKEN_DEFINITIONS = [
    {"value": "{{user_name}}", "label": "User name"},
    {"value": "{{book_title}}", "label": "Book title"},
    {"value": "{{book_shop_url}}", "label": "Shop URL"},
    {"value": "{{book_reader_url}}", "label": "Reader URL"},
]


class TemplateValidationError(ValueError):
    """Raised when template input fails validation."""


@dataclass
class TemplateLanguageView:
    key: str
    language: str
    html_body: str
    updated_at: Optional[str]


def allowed_languages() -> List[str]:
    return list(LANGUAGES)


def token_definitions() -> List[Dict[str, str]]:
    return TOKEN_DEFINITIONS.copy()


def template_definitions() -> Dict[str, Dict[str, str]]:
    return TEMPLATE_DEFINITIONS.copy()


def _normalize_language(language: str) -> str:
    candidate = (language or "").strip().lower()
    if candidate not in LANGUAGES:
        raise TemplateValidationError("unsupported_language")
    return candidate


def _validate_template_key(template_key: str) -> str:
    key = (template_key or "").strip().lower()
    if key not in TEMPLATE_DEFINITIONS:
        raise TemplateValidationError("unsupported_template")
    return key


def fetch_templates_context() -> Dict[str, List[Dict[str, object]]]:
    records = email_templates_repo.list_templates()
    lookup: Dict[tuple[str, str], TemplateLanguageView] = {}
    for record in records:
        lookup[(record.template_key, record.language)] = TemplateLanguageView(
            key=record.template_key,
            language=record.language,
            html_body=record.html_body or "",
            updated_at=record.updated_at.isoformat() if record.updated_at else None,
        )
    templates_payload: List[Dict[str, object]] = []
    for template_key, meta in TEMPLATE_DEFINITIONS.items():
        languages_payload: Dict[str, Dict[str, Optional[str]]] = {}
        for lang in LANGUAGES:
            view = lookup.get((template_key, lang))
            languages_payload[lang] = {
                "language": lang,
                "html": view.html_body if view else "",
                "updated_at": view.updated_at if view else None,
            }
        templates_payload.append({
            "key": template_key,
            "label": meta.get("label", template_key),
            "languages": languages_payload,
            "description": meta.get("description"),
        })
    return {"templates": templates_payload, "tokens": token_definitions(), "languages": allowed_languages()}


def save_template(template_key: str, language: str, html_body: str) -> TemplateLanguageView:
    normalized_key = _validate_template_key(template_key)
    normalized_language = _normalize_language(language)
    content = html_body or ""
    record = email_templates_repo.upsert_template(normalized_key, normalized_language, content)
    return TemplateLanguageView(
        key=record.template_key,
        language=record.language,
        html_body=record.html_body or "",
        updated_at=record.updated_at.isoformat() if record.updated_at else None,
    )


__all__ = [
    "TemplateValidationError",
    "fetch_templates_context",
    "save_template",
    "allowed_languages",
    "token_definitions",
    "template_definitions",
]
