"""
routes_ui.py

HTML UI routes for the users_books plugin.

Provides an administrator-facing management page to:
  - View the allow-list (users_books mappings) for a selected user.
  - Add a single (user_id, book_id) mapping.
  - Bulk add multiple book IDs.
  - Upsert (reconcile) the entire list against a provided set.
  - Delete individual mappings.

The UI is intentionally lightweight (pure HTML + vanilla JS) so it can
serve as a foundation for later enhancement (e.g., integrating a CSS
framework or moving to a richer client-side framework).

URL (mounted under the plugin blueprint prefix):
  GET /plugin/users_books/admin/ui   -> Render management page

Existing JSON Admin API used by the JS layer:
  GET    /plugin/users_books/admin/<user_id>/filters
  POST   /plugin/users_books/admin/<user_id>/filters
  DELETE /plugin/users_books/admin/<user_id>/filters/<book_id>
  POST   /plugin/users_books/admin/<user_id>/filters/bulk
  PUT    /plugin/users_books/admin/<user_id>/filters/upsert

Security:
  - Reuses utils.ensure_admin() for access control.
  - If user is not admin, returns 403 JSON or inline message.

Resilience:
  - If the Jinja template (users_books_admin.html) is not present (e.g.,
    deployment forgot to ship it), falls back to an inline HTML string
    using render_template_string to avoid breaking the plugin.

To customize the look & feel, create a file at:
  plugins/users_books/api/templates/users_books_admin.html
and copy the INLINE_TEMPLATE content as a starting point.

"""

from __future__ import annotations

from typing import Any

from flask import (
    jsonify,
    render_template,
    render_template_string,
)

from jinja2 import TemplateNotFound

from .. import utils
from ..utils import PermissionError
from ..logging_setup import get_logger

LOG = get_logger()

# ---------------------------------------------------------------------------
# Inline fallback template (kept minimal; customize via external template)
# ---------------------------------------------------------------------------

INLINE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>users_books Admin UI</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    :root {
      font-family: system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
      color-scheme: light dark;
    }
    body { margin: 1.5rem; line-height: 1.4; }
    h1 { font-size: 1.4rem; margin-bottom: .5rem; }
    h2 { font-size: 1.1rem; margin-top: 2rem; }
    fieldset { border: 1px solid #888; padding: .75rem 1rem 1rem; margin-bottom: 1.25rem; }
    legend { font-weight: 600; }
    label { display: inline-block; margin: .25rem 0 .25rem; font-weight: 500; }
    input[type=text], input[type=number], textarea {
      padding: .35rem .5rem;
      border: 1px solid #999;
      border-radius: 4px;
      min-width: 12rem;
      font-family: inherit;
      font-size: .95rem;
    }
    textarea { width: 100%; min-height: 6rem; resize: vertical; }
    button {
      cursor: pointer;
      padding: .45rem .85rem;
      border: 1px solid #555;
      border-radius: 4px;
      background: #2d6cdf;
      color: #fff;
      font-size: .85rem;
      font-weight: 500;
      margin-right: .5rem;
    }
    button.secondary { background: #666; }
    button.danger { background: #c0392b; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    table {
      border-collapse: collapse;
      margin-top: .75rem;
      width: 100%;
      max-width: 40rem;
      font-size: .9rem;
    }
    th, td {
      border: 1px solid #666;
      padding: .4rem .55rem;
      text-align: left;
    }
    th { background: #222; color: #eee; }
    tbody tr:nth-child(odd) { background: rgba(0,0,0,.05); }
    code { font-size: .85rem; }
    .status-bar {
      margin-top: 1rem;
      font-size: .8rem;
      white-space: pre-wrap;
      background: rgba(0,0,0,.08);
      padding: .5rem .75rem;
      border-radius: 4px;
      max-width: 50rem;
      overflow-x: auto;
    }
    .flex { display: flex; gap: .75rem; flex-wrap: wrap; align-items: flex-end; }
    .muted { opacity: .7; }
    .pill {
      display: inline-block;
      background: #444;
      color: #fff;
      padding: .2rem .5rem;
      border-radius: 999px;
      font-size: .7rem;
      margin-left: .5rem;
      vertical-align: middle;
    }
  </style>
</head>
<body>
  <h1>
    users_books Admin
    <span class="pill">UI</span>
  </h1>
  <p class="muted">Manage per-user book allow-list entries stored in the <code>users_books</code> table.</p>

  <fieldset>
    <legend>Target User</legend>
    <div class="flex">
      <label>
        User ID
        <input id="userIdInput" type="number" min="1" placeholder="e.g. 1">
      </label>
      <button id="loadBtn" type="button">Load Mappings</button>
      <button id="clearBtn" type="button" class="secondary">Clear</button>
    </div>
  </fieldset>

  <fieldset>
    <legend>Current Allow-List</legend>
    <div id="currentUserInfo" class="muted">No user loaded.</div>
    <table id="mappingTable" style="display:none;">
      <thead>
        <tr>
          <th style="width:6rem;">Book ID</th>
          <th style="width:3rem;">Remove</th>
        </tr>
      </thead>
      <tbody id="mappingBody"></tbody>
    </table>
  </fieldset>

  <fieldset>
    <legend>Add Single Mapping</legend>
    <div class="flex">
      <label>
        Book ID
        <input id="singleBookId" type="number" min="1" placeholder="Book ID">
      </label>
      <button id="addSingleBtn" type="button">Add</button>
    </div>
  </fieldset>

  <fieldset>
    <legend>Bulk Add</legend>
    <label>Book IDs (comma / whitespace separated)</label>
    <textarea id="bulkIds" placeholder="12, 15, 99  101"></textarea>
    <button id="bulkAddBtn" type="button">Bulk Add</button>
  </fieldset>

  <fieldset>
    <legend>Upsert (Reconcile)</legend>
    <p class="muted" style="margin-top:0;">Final list after upsert will match exactly the IDs provided below.</p>
    <textarea id="upsertIds" placeholder="Enter desired full set of book IDs..."></textarea>
    <button id="upsertBtn" type="button" class="danger">Upsert (Destructive)</button>
  </fieldset>

  <h2>Status / Logs</h2>
  <div id="status" class="status-bar"></div>

  <script>
    const els = {
      userIdInput: document.getElementById('userIdInput'),
      loadBtn: document.getElementById('loadBtn'),
      clearBtn: document.getElementById('clearBtn'),
      mappingTable: document.getElementById('mappingTable'),
      mappingBody: document.getElementById('mappingBody'),
      currentUserInfo: document.getElementById('currentUserInfo'),
      singleBookId: document.getElementById('singleBookId'),
      addSingleBtn: document.getElementById('addSingleBtn'),
      bulkIds: document.getElementById('bulkIds'),
      bulkAddBtn: document.getElementById('bulkAddBtn'),
      upsertIds: document.getElementById('upsertIds'),
      upsertBtn: document.getElementById('upsertBtn'),
      status: document.getElementById('status'),
    };

    function log(msg, clear=false) {
      const ts = new Date().toISOString();
      if (clear) {
        els.status.textContent = `[${ts}] ${msg}`;
      } else {
        els.status.textContent += `\\n[${ts}] ${msg}`;
      }
      els.status.scrollTop = els.status.scrollHeight;
    }

    function parseIds(text) {
      return [...new Set(text.split(/[^0-9]+/).map(s => s.trim()).filter(Boolean).map(Number))]
        .filter(n => Number.isInteger(n) && n > 0)
        .sort((a,b)=>a-b);
    }

    function apiBase(userId) {
      return `/plugin/users_books/admin/${userId}/filters`;
    }

    function requireUserId() {
      const uid = Number(els.userIdInput.value);
      if (!Number.isInteger(uid) || uid <= 0) {
        throw new Error("Enter a valid positive integer user id first.");
      }
      return uid;
    }

    async function loadMappings() {
      let uid;
      try {
        uid = requireUserId();
      } catch (e) {
        log(e.message, true);
        return;
      }
      log(`Loading mappings for user ${uid}...`, true);
      try {
        const r = await fetch(apiBase(uid));
        if (!r.ok) {
          log(`Failed to load mappings: HTTP ${r.status}`);
          return;
        }
        const data = await r.json();
        renderMappings(uid, data.allowed_book_ids || []);
        log(`Loaded ${data.count||0} mapping(s).`);
      } catch (e) {
        log(`Error loading mappings: ${e}`);
      }
    }

    function renderMappings(userId, bookIds) {
      els.mappingBody.innerHTML = "";
      if (!bookIds.length) {
        els.mappingTable.style.display = "none";
        els.currentUserInfo.textContent = `User ${userId} has no allowed book mappings.`;
        return;
      }
      els.mappingTable.style.display = "";
      els.currentUserInfo.textContent = `User ${userId} (${bookIds.length} mapping(s))`;
      for (const bid of bookIds) {
        const tr = document.createElement('tr');
        const tdId = document.createElement('td');
        tdId.textContent = bid;
        const tdRemove = document.createElement('td');
        const btn = document.createElement('button');
        btn.textContent = "✕";
        btn.style.background = "#b33939";
        btn.title = `Remove mapping (book ${bid})`;
        btn.onclick = () => deleteMapping(userId, bid);
        tdRemove.appendChild(btn);
        tr.appendChild(tdId);
        tr.appendChild(tdRemove);
        els.mappingBody.appendChild(tr);
      }
    }

    async function deleteMapping(userId, bookId) {
      if (!confirm(`Remove mapping (user ${userId}, book ${bookId})?`)) return;
      log(`Deleting mapping book=${bookId}...`);
      try {
        const r = await fetch(`${apiBase(userId)}/${bookId}`, { method: 'DELETE' });
        const data = await r.json();
        log(`Delete status: ${data.status}`);
        await loadMappings();
      } catch (e) {
        log(`Error deleting: ${e}`);
      }
    }

    async function addSingle() {
      let uid;
      try { uid = requireUserId(); } catch (e) { log(e.message, true); return; }
      const bookId = Number(els.singleBookId.value);
      if (!Number.isInteger(bookId) || bookId <= 0) {
        log("Enter a valid positive integer book id.", true);
        return;
      }
      log(`Adding mapping (user=${uid}, book=${bookId})...`);
      try {
        const r = await fetch(apiBase(uid), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ book_id: bookId })
        });
        const data = await r.json();
        log(`Add result: ${data.status}`);
        els.singleBookId.value = "";
        await loadMappings();
      } catch (e) {
        log(`Error adding single: ${e}`);
      }
    }

    async function bulkAdd() {
      let uid;
      try { uid = requireUserId(); } catch (e) { log(e.message, true); return; }
      const ids = parseIds(els.bulkIds.value);
      if (!ids.length) { log("Provide at least one valid book id for bulk add.", true); return; }
      log(`Bulk adding ${ids.length} id(s)...`);
      try {
        const r = await fetch(`${apiBase(uid)}/bulk`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ book_ids: ids })
        });
        const data = await r.json();
        log(`Bulk added: ${data.added}, existing: ${data.skipped_existing}`);
        els.bulkIds.value = "";
        await loadMappings();
      } catch (e) {
        log(`Error bulk adding: ${e}`);
      }
    }

    async function upsert() {
      if (!confirm("This will reconcile (add/remove) to match the supplied set. Continue?")) return;
      let uid;
      try { uid = requireUserId(); } catch (e) { log(e.message, true); return; }
      const ids = parseIds(els.upsertIds.value);
      if (!ids.length) { log("Provide at least one valid book id for upsert.", true); return; }
      log(`Upserting to ${ids.length} total id(s)...`);
      try {
        const r = await fetch(`${apiBase(uid)}/upsert`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ book_ids: ids })
        });
        const data = await r.json();
        log(`Upsert added=${data.added} removed=${data.removed} final_total=${data.final_total}`);
        await loadMappings();
      } catch (e) {
        log(`Error upserting: ${e}`);
      }
    }

    function clearAll() {
      els.mappingBody.innerHTML = "";
      els.mappingTable.style.display = "none";
      els.currentUserInfo.textContent = "No user loaded.";
      log("Cleared state.", true);
    }

    // Event bindings
    els.loadBtn.addEventListener('click', loadMappings);
    els.clearBtn.addEventListener('click', clearAll);
    els.addSingleBtn.addEventListener('click', addSingle);
    els.bulkAddBtn.addEventListener('click', bulkAdd);
    els.upsertBtn.addEventListener('click', upsert);

    // Enter key on userId triggers load
    els.userIdInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') loadMappings();
    });
  </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register(bp):
    """
    Register the UI route(s) on the provided blueprint.

    The admin UI is intentionally served under /admin/ui (HTML) to
    distinguish it from the JSON endpoints with the same admin prefix.
    """

    @bp.route("/admin/ui", methods=["GET"])
    def admin_ui():
        try:
            # Ensure caller is admin
            utils.ensure_admin()
        except PermissionError as exc:
            # Provide a minimal inline notice instead of JSON (we're an HTML page)
            return (
                f"<h1>403 Forbidden</h1><p>{exc}</p><p>"
                "You must have admin privileges to access this page.</p>",
                403,
            )

        # Try using an external template first (override-friendly).
        template_name = "users_books_admin.html"
        try:
            return render_template(template_name)
        except TemplateNotFound:
            LOG.debug("Template '%s' not found; falling back to inline.", template_name)
            return render_template_string(INLINE_TEMPLATE)


__all__ = ["register"]
