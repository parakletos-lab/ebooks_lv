"""Operator manual loader (non-technical docs/operator).

Reads the current markdown files at request-time so updates to files are
reflected immediately.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.utils.logging import get_logger

LOG = get_logger("operator_manual_service")


def _repo_root() -> Path:
    # Local checkout: <repo>/app/services/...
    # Docker image:   /app/app/services/...
    return Path(__file__).resolve().parents[2]


def _docs_dir() -> Path:
    return _repo_root() / "docs" / "operator"


def _language_suffix(language: str) -> str:
    lang = (language or "").strip().lower()
    if lang.startswith("lv"):
        return "_lv"
    if lang.startswith("ru"):
        return "_ru"
    return ""


def _manual_sections() -> Iterable[str]:
    # Keep the operator-facing flow: hub -> users -> books.
    return ("admin_hub", "user_management", "books_management")


def load_operator_manual_markdown(language: str) -> str:
    suffix = _language_suffix(language)
    parts: list[str] = []
    base_dir = _docs_dir()

    for name in _manual_sections():
        filename = f"{name}{suffix}.md"
        path = base_dir / filename
        if not path.exists():
            # Fall back to English if localized file is missing.
            fallback = base_dir / f"{name}.md"
            path = fallback
        try:
            parts.append(path.read_text(encoding="utf-8"))
        except Exception:
            LOG.exception("Failed reading operator manual section %s", path)
            parts.append(f"# {name}\n\n(Unable to load: {path.name})\n")

    return "\n\n---\n\n".join(parts)


def render_operator_manual_html(language: str) -> str:
    markdown_text = load_operator_manual_markdown(language)

    try:
        from markdown2 import Markdown  # type: ignore

        md = Markdown(extras=["fenced-code-blocks", "tables", "strike", "task_list"])
        return md.convert(markdown_text)
    except Exception:
        # Keep UI functional even if markdown2 is unavailable.
        import html

        escaped = html.escape(markdown_text)
        return f"<pre style=\"white-space: pre-wrap;\">{escaped}</pre>"


__all__ = [
    "load_operator_manual_markdown",
    "render_operator_manual_html",
]
