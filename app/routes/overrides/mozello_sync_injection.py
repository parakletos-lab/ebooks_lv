"""Mozello sync button injection for book detail pages.

Ensures the admin-only "Sync to Mozello" button appears even when templates
skip the layout ``block js`` (e.g., by overriding without ``super()``).
"""
from __future__ import annotations

import json
import re
from typing import Any, Tuple
from string import Template

from flask import Request, Response, request

try:  # pragma: no cover - Flask-Babel optional in tests
    from flask_babel import gettext as _  # type: ignore
except Exception:  # pragma: no cover
    def _fallback_gettext(message, **kwargs):
        if kwargs:
            try:
                return message % kwargs
            except Exception:
                return message
        return message

    _ = _fallback_gettext  # type: ignore

from app.utils.identity import is_admin_user
from app.utils.logging import get_logger

LOG = get_logger("mozello_sync_injection")

MARKER = "ub-sync-to-mozello"
ANCHOR = 'id="edit_book"'
MAX_BODY_SIZE = 1_500_000  # bytes


def _js_string(value: str) -> str:
    try:
        return json.dumps(value)
    except Exception:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


def _is_target_request(req: Request) -> bool:
    path = (req.path or "").rstrip("/")
    return bool(re.match(r"^/book/\d+$", path))


def _should_skip(response: Response) -> Tuple[bool, str]:
    if not _is_target_request(request):
        return True, "not_detail"
    if not is_admin_user():
        return True, "not_admin"
    if response.status_code != 200:
        return True, f"status_{response.status_code}"
    ctype = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in ctype:
        return True, f"ctype_{ctype or 'none'}"
    body = response.get_data(as_text=False)
    if not body:
        return True, "empty_body"
    if len(body) > MAX_BODY_SIZE:
        return True, "body_too_large"
    if MARKER.encode("utf-8") in body:
        return True, "marker_present"
    if ANCHOR.encode("utf-8") not in body:
        return True, "anchor_missing"
    return False, "ok"


def _build_snippet() -> bytes:
    sync_label = _("Sync to Mozello")
    syncing_label = _("Syncing to Mozello...")
    success_msg = _("Synced to Mozello.")
    failure_msg = _("Mozello sync failed.")

    script = Template(
        """
<script>
(function() {
    'use strict';
    if (window.__ubMozelloSyncHook) { return; }
    window.__ubMozelloSyncHook = true;
    function resolveBookId() {
        var match = (window.location.pathname || '').match(/^\/book\/(\d+)/);
        if (match) { return match[1]; }
        var editLink = document.getElementById('edit_book');
        if (editLink && editLink.getAttribute('href')) {
            var hrefMatch = editLink.getAttribute('href').match(/(\d+)/);
            if (hrefMatch) { return hrefMatch[1]; }
        }
        return null;
    }
    var bookId = resolveBookId();
    var busy = false;
    var buttons = [];
    var syncLabel = $sync_label;
    var syncingLabel = $syncing_label;
    var successMsg = $success_msg;
    var failureMsg = $failure_msg;
    function flash(type, message) {
        if (typeof handleResponse === 'function') {
            handleResponse([{ type: type, message: message }]);
        } else {
            var logger = type === 'danger' ? console.error : console.log;
            logger(message);
        }
    }
    function setBusy(state) {
        busy = state;
        buttons.forEach(function(btn) {
            btn.disabled = state;
            btn.classList.toggle('is-busy', state);
            var label = btn.querySelector('.ub-mz-label');
            if (label) {
                label.textContent = state ? syncingLabel : syncLabel;
            }
        });
    }
    async function syncMozello() {
        if (busy) { return; }
        if (!bookId) {
            bookId = resolveBookId();
            if (!bookId) { return; }
        }
        setBusy(true);
        try {
            var resp = await fetch('/admin/ebookslv/books/api/export_one/' + bookId, { method: 'POST' });
            var data = await resp.json().catch(function() { return null; });
            if (!resp.ok) {
                var reason = data && data.message ? data.message : resp.statusText;
                throw new Error(reason || '');
            }
            flash('success', successMsg);
        } catch (err) {
            var msg = failureMsg;
            if (err && err.message) { msg += ' ' + err.message; }
            flash('danger', msg);
        } finally {
            setBusy(false);
        }
    }
    function createButton(id) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-warning btn-sm ub-sync-to-mozello';
        btn.id = id;
        btn.innerHTML = '<span class="glyphicon glyphicon-flash" aria-hidden="true"></span><span class="ub-mz-label">' + syncLabel + '</span>';
        btn.addEventListener('click', syncMozello);
        buttons.push(btn);
        return btn;
    }
    function insertToolbarButton() {
        var editBtn = document.getElementById('edit_book');
        if (!editBtn || !editBtn.parentNode) { return; }
        if (document.getElementById('ub-sync-to-mozello-detail')) { return; }
        var btn = createButton('ub-sync-to-mozello-detail');
        editBtn.parentNode.appendChild(btn);
    }
    function init() {
        insertToolbarButton();
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    if (window.jQuery && typeof window.jQuery === 'function' && window.jQuery.fn && window.jQuery.fn.modal) {
        window.jQuery('#bookDetailsModal').on('shown.bs.modal', function(evt) {
            var target = evt && evt.relatedTarget;
            var href = target && target.getAttribute && target.getAttribute('href');
            var match = href && href.match(/\/book\/(\d+)/);
            if (match) {
                bookId = match[1];
            } else {
                bookId = resolveBookId();
            }
            insertToolbarButton();
        });
    }
})();
</script>
"""
    )
    script = script.substitute(
        sync_label=_js_string(sync_label),
        syncing_label=_js_string(syncing_label),
        success_msg=_js_string(success_msg),
        failure_msg=_js_string(failure_msg),
    )
    return script.encode("utf-8")


def _inject(response: Response) -> Response:
    body = response.get_data(as_text=False)
    if not body:
        return response
    snippet = _build_snippet()
    lower_body = body.lower()
    closing = lower_body.rfind(b"</body>")
    if closing == -1:
        response.set_data(body + snippet)
        return response
    response.set_data(body[:closing] + snippet + body[closing:])
    return response


def register_mozello_sync_injection(app: Any) -> None:  # pragma: no cover - glue code
    if getattr(app, "_mozello_sync_injection", False):  # type: ignore[attr-defined]
        return

    @app.after_request  # type: ignore[misc]
    def _mozello_sync_after(resp: Response):  # type: ignore[override]
        skip, reason = _should_skip(resp)
        if skip:
            LOG.debug("mozello sync injection skip: %s", reason)
            return resp
        return _inject(resp)

    setattr(app, "_mozello_sync_injection", True)
    LOG.debug("Mozello sync after_request hook registered")


__all__ = ["register_mozello_sync_injection"]
