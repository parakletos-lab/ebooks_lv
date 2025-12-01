"""Template-driven email delivery helpers for Mozello purchases."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlencode

from flask import has_request_context, request
from jinja2 import BaseLoader, Environment, TemplateError

from app import config as app_config
from app.db.repositories import email_templates_repo
from app.services.email_templates_service import allowed_languages
from app.utils.logging import get_logger

try:  # pragma: no cover - runtime dependency
    from cps import config as cw_config  # type: ignore
    from cps.tasks.mail import TaskEmail  # type: ignore
    from cps.services.worker import WorkerThread  # type: ignore
except Exception:  # pragma: no cover - unit tests without Calibre runtime
    cw_config = None  # type: ignore

    class TaskEmail:  # type: ignore
        def __init__(self, *args, **kwargs):
            raise RuntimeError("TaskEmail unavailable outside Calibre-Web runtime")

    class WorkerThread:  # type: ignore
        @classmethod
        def add(cls, *args, **kwargs):
            raise RuntimeError("WorkerThread unavailable outside Calibre-Web runtime")


LOG = get_logger("email_delivery")
_TEMPLATE_KEY = "book_purchase"
_LANG_ORDER = tuple(allowed_languages()) or ("en",)
_JINJA_ENV = Environment(loader=BaseLoader(), autoescape=False, trim_blocks=True, lstrip_blocks=True)
_HTML_BREAK_PATTERN = re.compile(r"</p>|<br\s*/?>", re.IGNORECASE)
_TAG_PATTERN = re.compile(r"<[^>]+>")


class EmailDeliveryError(RuntimeError):
    """Base error for email delivery failures."""


class TemplateMissingError(EmailDeliveryError):
    """Raised when the requested template is not configured."""


class MailNotConfiguredError(EmailDeliveryError):
    """Raised when SMTP settings are absent."""


class EmailQueueError(EmailDeliveryError):
    """Raised when WorkerThread cannot accept the task."""


@dataclass(frozen=True)
class BookDeliveryItem:
    """Minimal metadata required to build book links inside purchase emails."""

    book_id: int
    title: str
    language_code: Optional[str] = None


class HtmlTaskEmail(TaskEmail):
    """TaskEmail extension that attaches HTML alternatives."""

    def __init__(
        self,
        *,
        html_body: str,
        subject: str,
        settings: Dict[str, object],
        recipient: str,
        text_body: str,
        task_message: str,
    ) -> None:
        self._html_body = html_body or ""
        super().__init__(
            subject,
            filepath=None,
            attachment=None,
            settings=settings,
            recipient=recipient,
            task_message=task_message,
            text=text_body,
        )

    def prepare_message(self):  # pragma: no cover - exercised via TaskEmail
        message = super().prepare_message()
        if message and self._html_body:
            message.add_alternative(self._html_body, subtype="html")
        return message


def absolute_site_url(path: str) -> str:
    """Return an absolute URL using request context or configured domain."""

    if not path:
        return ""
    candidate = path.strip()
    if candidate.startswith(("http://", "https://")):
        return candidate
    if not candidate.startswith("/"):
        candidate = f"/{candidate}"
    base_url: Optional[str] = None
    if has_request_context():
        try:
            base_url = request.url_root.rstrip("/")
        except Exception:  # pragma: no cover - defensive guard
            base_url = None
    if not base_url:
        domain = app_config.public_domain()
        if domain:
            if domain.startswith(("http://", "https://")):
                base_url = domain.rstrip("/")
            else:
                base_url = f"https://{domain.strip('/')}"
    if not base_url:
        return candidate
    return f"{base_url}{candidate}"


def _render_template(template_str: str, context: Dict[str, object]) -> str:
    try:
        template = _JINJA_ENV.from_string(template_str or "")
        return template.render(**context)
    except TemplateError as exc:  # pragma: no cover - guarded by admin UI validation
        raise EmailDeliveryError("template_render_failed") from exc


def _html_to_text(value: str) -> str:
    if not value:
        return ""
    working = _HTML_BREAK_PATTERN.sub("\n", value)
    working = _TAG_PATTERN.sub("", working)
    working = html.unescape(working)
    working = re.sub(r"\n{3,}", "\n\n", working)
    return working.strip()


def _mail_settings() -> Dict[str, object]:
    if cw_config is None:
        raise MailNotConfiguredError("mail_runtime_missing")
    if not cw_config.get_mail_server_configured():  # type: ignore[attr-defined]
        raise MailNotConfiguredError("mail_not_configured")
    settings = cw_config.get_mail_settings()  # type: ignore[attr-defined]
    if not settings:
        raise MailNotConfiguredError("mail_settings_missing")
    return settings


def _load_template(language: str):
    record = email_templates_repo.get_template(_TEMPLATE_KEY, language)
    if record:
        return record
    for fallback in _LANG_ORDER:
        if fallback == language:
            continue
        record = email_templates_repo.get_template(_TEMPLATE_KEY, fallback)
        if record:
            return record
    raise TemplateMissingError("book_purchase_template_missing")


def _resolve_language(preferred: Optional[str], books: Sequence[BookDeliveryItem]) -> str:
    candidates: List[str] = []
    if preferred:
        candidates.append(preferred)
    for item in books:
        if item.language_code:
            candidates.append(item.language_code)
    for candidate in candidates:
        normalized = candidate.strip().lower()
        if normalized in _LANG_ORDER:
            return normalized
    return _LANG_ORDER[0]


def _build_book_links(
    books: Sequence[BookDeliveryItem],
    auth_token: Optional[str],
) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    for item in books:
        try:
            book_id = int(item.book_id)
        except (TypeError, ValueError):
            continue
        display = item.title or f"Book {book_id}"
        detail_path = f"/book/{book_id}"
        login_base = absolute_site_url("/login")
        params = {"next": detail_path}
        if auth_token:
            params["auth"] = auth_token
        reader_url = f"{login_base}?{urlencode(params)}"
        links.append({
            "title": display,
            "reader_url": reader_url,
            "detail_url": absolute_site_url(detail_path),
        })
    return links


def _render_books_tokens(links: List[Dict[str, str]]) -> Dict[str, str]:
    if not links:
        placeholder = "Books will appear in your library shortly."
        return {"html": f"<li>{html.escape(placeholder)}</li>", "text": placeholder}
    html_items: List[str] = []
    text_items: List[str] = []
    for link in links:
        safe_title = html.escape(link["title"])
        href = link["reader_url"]
        html_items.append(f'<li><a href="{href}">{safe_title}</a></li>')
        text_items.append(f"- {link['title']}: {href}")
    return {"html": "\n".join(html_items), "text": "\n".join(text_items)}


def _queue_email_task(user_label: str, task: HtmlTaskEmail) -> None:
    try:
        WorkerThread.add(user_label or "System", task)
    except Exception as exc:  # pragma: no cover - WorkerThread handles errors internally
        raise EmailQueueError("worker_queue_failed") from exc


def send_book_purchase_email(
    *,
    recipient_email: str,
    user_name: str,
    books: Sequence[BookDeliveryItem],
    shop_url: Optional[str],
    my_books_url: Optional[str] = None,
    auth_token: Optional[str] = None,
    preferred_language: Optional[str] = None,
) -> Dict[str, object]:
    """Render and enqueue the Mozello purchase notification email."""

    if not recipient_email:
        raise EmailDeliveryError("recipient_required")
    book_items = list(books)
    language = _resolve_language(preferred_language, book_items)
    template = _load_template(language)
    links = _build_book_links(book_items, auth_token)
    book_tokens = _render_books_tokens(links)
    context = {
        "user_name": (user_name or recipient_email).strip() or recipient_email,
        "shop_url": (shop_url or "").strip(),
        "my_books": (my_books_url or absolute_site_url("/catalog/my-books")),
        "books": book_tokens["html"],
    }
    subject_context = context.copy()
    subject_context["books"] = book_tokens["text"]

    subject_rendered = _render_template(template.subject or "Your ebooks are ready", subject_context).strip()
    html_body = _render_template(template.html_body or "", context)
    text_variant_html = _render_template(template.html_body or "", subject_context)
    text_body = _html_to_text(text_variant_html)

    task = HtmlTaskEmail(
        html_body=html_body,
        subject=subject_rendered or "Your ebooks are ready",
        settings=_mail_settings(),
        recipient=recipient_email,
        text_body=text_body or book_tokens["text"],
        task_message=f"Mozello purchase → {recipient_email}",
    )
    _queue_email_task(user_name or recipient_email, task)
    LOG.info(
        "Queued Mozello purchase email email=%s language=%s books=%s",
        recipient_email,
        language,
        len(book_items),
    )
    return {
        "language": language,
        "book_count": len(book_items),
        "queued": True,
    }


__all__ = [
    "send_book_purchase_email",
    "BookDeliveryItem",
    "EmailDeliveryError",
    "TemplateMissingError",
    "MailNotConfiguredError",
    "EmailQueueError",
    "absolute_site_url",
]
