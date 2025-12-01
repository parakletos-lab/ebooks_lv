"""Repository helpers for stored email templates."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import text

from app.db import plugin_session
from app.db.engine import get_engine
from app.db.models import EmailTemplate
from app.utils.logging import get_logger

LOG = get_logger("email_templates_repo")
_SUBJECT_COLUMN_READY = False


def _ensure_subject_column() -> None:
    global _SUBJECT_COLUMN_READY
    if _SUBJECT_COLUMN_READY:
        return
    try:
        engine = get_engine()
        with engine.begin() as conn:  # type: ignore[assignment]
            columns = [row[1] for row in conn.execute(text("PRAGMA table_info(email_templates)"))]
            if "subject" not in columns:
                LOG.info("Adding email_templates.subject column")
                conn.execute(
                    text(
                        "ALTER TABLE email_templates "
                        "ADD COLUMN subject VARCHAR(255) NOT NULL DEFAULT ''"
                    )
                )
    except Exception as exc:  # pragma: no cover - best-effort guard
        LOG.error("Email templates schema migration failed: %s", exc)
    finally:
        _SUBJECT_COLUMN_READY = True


def get_template(template_key: str, language: str) -> Optional[EmailTemplate]:
    _ensure_subject_column()
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
    _ensure_subject_column()
    with plugin_session() as session:
        query = session.query(EmailTemplate)
        if template_key:
            query = query.filter(EmailTemplate.template_key == template_key)
        return query.all()


def upsert_template(
    template_key: str,
    language: str,
    html_body: str,
    subject: str,
) -> EmailTemplate:
    _ensure_subject_column()
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
            record.subject = subject
            return record
        record = EmailTemplate(
            template_key=template_key,
            language=language,
            html_body=html_body,
            subject=subject,
        )
        session.add(record)
        return record


__all__ = ["get_template", "list_templates", "upsert_template"]
