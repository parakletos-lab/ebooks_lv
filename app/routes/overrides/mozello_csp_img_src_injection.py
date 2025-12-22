"""Extend CSP img-src to allow Mozello-hosted images.

Calibre-Web ships with a strict CSP on most pages:
  img-src 'self' data:

When we render Mozello product images (stored in `mz_pictures`), they may be
hosted on https://*.mozfiles.com. The book details modal in catalog pages runs
within the catalog document, so we must allow these origins on the catalog page
CSP (not only on /book/<id> responses).

We keep this scoped to images only and to the mozfiles domain wildcard.
"""

from __future__ import annotations

from typing import Any, List

from flask import Request, Response, request

from app.utils.logging import get_logger

LOG = get_logger("mozello_csp_img_src_injection")


_ALLOWED_IMG_SRC: List[str] = ["https://*.mozfiles.com"]


def _is_html_response(resp: Response) -> bool:
    if resp.status_code != 200:
        return False
    ctype = (resp.headers.get("Content-Type") or "").lower()
    return "text/html" in ctype


def _extend_csp_img_src(resp: Response) -> bool:
    csp = resp.headers.get("Content-Security-Policy")
    if not csp:
        return False

    # Normalize any stray newlines; CSP is a single header value.
    csp = " ".join(csp.split())
    parts = [p.strip() for p in csp.split(";") if p.strip()]

    new_parts: List[str] = []
    updated = False

    for part in parts:
        tokens = part.split()
        if not tokens:
            continue

        if tokens[0].lower() != "img-src":
            new_parts.append(part)
            continue

        existing = set(tokens[1:])
        for src in _ALLOWED_IMG_SRC:
            if src not in existing:
                tokens.append(src)
                existing.add(src)
                updated = True

        new_parts.append(" ".join(tokens))

    if not updated:
        return False

    resp.headers["Content-Security-Policy"] = "; ".join(new_parts) + ";"
    return True


def register_mozello_csp_img_src_injection(app: Any) -> None:  # pragma: no cover - glue code
    if getattr(app, "_mozello_csp_img_src_injection", False):  # type: ignore[attr-defined]
        return

    @app.after_request  # type: ignore[misc]
    def _after(resp: Response):  # type: ignore[override]
        if not _is_html_response(resp):
            return resp

        changed = _extend_csp_img_src(resp)
        if changed:
            LOG.debug("Extended CSP img-src for %s", (request.path or ""))
        return resp

    # Ensure this hook runs LAST (Flask runs after_request in reverse order).
    try:
        funcs = getattr(app, "after_request_funcs", {}).get(None)
        if isinstance(funcs, list) and funcs and funcs[-1] is _after:
            funcs.insert(0, funcs.pop())
    except Exception:
        pass

    setattr(app, "_mozello_csp_img_src_injection", True)


__all__ = ["register_mozello_csp_img_src_injection"]
