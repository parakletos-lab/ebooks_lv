"""Repository helpers for stored email templates."""
from __future__ import annotations

from typing import List, Optional

from app.db import plugin_session
from app.db.models import EmailTemplate


def get_template(template_key: str, language: str) -> Optional[EmailTemplate]:
    with plugin_session() as session:
        return (
            session.query(EmailTemplate)
            .filter(
                EmailTemplate.template_key == template_key,
                EmailTemplate.language == language,
            )
            .one_or_none()
        )


def list_templates(template_key: Optional[str] = None) -> List[EmailTemplate]:
    with plugin_session() as session:
        query = session.query(EmailTemplate)
        if template_key:
            query = query.filter(EmailTemplate.template_key == template_key)
        return query.all()


def upsert_template(template_key: str, language: str, html_body: str) -> EmailTemplate:
    with plugin_session() as session:
        record = (
            session.query(EmailTemplate)
            .filter(
                EmailTemplate.template_key == template_key,
                EmailTemplate.language == language,
            )
            .one_or_none()
        )
        if record:
            record.html_body = html_body
            return record
        record = EmailTemplate(
            template_key=template_key,
            language=language,
            html_body=html_body,
        )
        session.add(record)
        return record


__all__ = ["get_template", "list_templates", "upsert_template"]
