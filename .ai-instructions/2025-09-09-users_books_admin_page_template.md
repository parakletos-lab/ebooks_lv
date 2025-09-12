# users_books Admin Page Replication Template
Date: 2025-09-09  
Author: (add your name/initials)

This document is a reusable instruction template for creating additional Calibre-Web plugin admin UI pages modeled after the `users_books` admin management interface. Use it whenever you need to add a new CRUD-style page that:

- Integrates with Calibre-Web’s `layout.html` for a seamless theme.
- Provides a rich, JS-enhanced interface without external frameworks.
- Exposes RESTful admin endpoints with proper authorization.
- Uses layered architecture (routes → services → db/models) with minimal coupling.

---

## 1. What You Are Building

A new admin page that allows privileged users (Calibre-Web admins) to manage a resource:  
Examples:
- user → tag exceptions  
- curated collections  
- feature toggles  
- entitlement groups  

Each page typically includes:
1. Discovery lists (e.g., all users, all books).
2. A selection → action workflow (add / remove / batch).
3. A consolidated table view of existing mappings or records.
4. Inline delete / update actions.
5. A status/log pane.

---

## 2. Design Principles

| Principle              | Guideline |
|------------------------|----------|
| Separation of Concerns | Keep business logic out of route handlers (use `services.py`). |
| Idempotence            | Re-run init safely (idempotent DB creation, safe plugin loading). |
| Defensive Access       | All admin endpoints must enforce an admin check (`utils.ensure_admin()`). |
| Performance            | Offer `?limit=` for large result sets; add pagination later if needed. |
| Minimal JS             | Use vanilla JS (no React/Vue) to reduce bundle/maintenance overhead. |
| Progressive Failure    | If metadata DB is missing or empty, return empty arrays instead of 500 errors. |
| Observability          | Log key operations (add/remove/upsert) clearly in the UI status area. |

---

## 3. Directory / File Layout (Recommended)

```
plugins/<plugin_name>/
  api/
    routes_<feature>.py
    templates/
      <feature>_admin.html
  services_<feature>.py          (or integrate into existing services.py if small)
  models_<feature>.py            (if new tables are needed)
  db.py                          (shared engine/session mgmt stays centralized)
  utils.py                       (auth/user helpers reused)
  __init__.py                    (init_app orchestrates: init_engine, blueprint, hooks)
```

---

## 4. Endpoint Patterns

| Purpose                     | Method | Path                                                              | Notes |
|----------------------------|--------|-------------------------------------------------------------------|-------|
| List all records           | GET    | /plugin/<plugin>/admin/<resource_plural>                          | Optional `?limit=` |
| List expanded mappings     | GET    | /plugin/<plugin>/admin/<resource>_full                            | Joins + display fields |
| Create single mapping      | POST   | /plugin/<plugin>/admin/<id>/filters (if user-scoped like current) | JSON body `{ key: value }` |
| Bulk add (optional)        | POST   | /plugin/<plugin>/admin/<id>/filters/bulk                          | `{ keys: [] }` |
| Reconcile (upsert)         | PUT    | /plugin/<plugin>/admin/<id>/filters/upsert                        | Destroys absent |
| Delete one                 | DELETE | /plugin/<plugin>/admin/<id>/filters/<sub_id>                      | Targeted removal |
| Full mapping delete        | DELETE | /plugin/<plugin>/admin/<resource>_full/<id>/<sub_id>              | Convenience |

Admin guard call must wrap every route. Return JSON with consistent shapes.

---

## 5. Authorization

Use the existing pattern:

```
def _require_admin():
    try:
        utils.ensure_admin()
        return True
    except PermissionError as exc:
        return jsonify({"error": str(exc)}), 403
```

Never trust client-provided assumptions—always verify on the server.

---

## 6. Data Access & Services

Layer design:
1. `routes_<feature>.py`  
   - Parse/validate input
   - Call services
   - Shape JSON response

2. `services_<feature>.py`  
   - Compose DB queries
   - Enforce uniqueness / reconciliation
   - Return plain Python types (lists, dicts, bools)

3. `models_<feature>.py`  
   - Define ORM models with explicit indices & uniqueness constraints  
   - Avoid foreign keys to Calibre core tables unless absolutely safe

4. `db.py`  
   - Supplies `plugin_session()` context manager.

---

## 7. Template Structure (`<feature>_admin.html`)

Sections to include:
1. Heading + brief explanation
2. Filterable checkbox list A (e.g., users)
3. Filterable checkbox list B (e.g., books or tags)
4. Action column (Add selections, Refresh, Clear)
5. Mappings table (expanded, join-enriched data)
6. Log / status area

Should extend Calibre-Web’s primary layout:

```
{% extends "layout.html" %}
{% set title = '<Feature> Admin' %}
{% block body %}
  <!-- UI layout -->
{% endblock %}
```

---

## 8. JavaScript Pattern

Recommended skeleton:

```
(function(){
  "use strict";

  // 1. Element refs
  // 2. Logging helper
  // 3. Fetch JSON helper
  // 4. Render functions (lists + mappings)
  // 5. Selection helpers
  // 6. Action handlers (add, delete, refresh)
  // 7. Event bindings
  // 8. Initial load bootstrap
})();
```

Avoid global variables. Use small functional helpers:
- `fetchJSON(url)`
- `escapeHtml(str)`
- `selectedValues(container)`

---

## 9. Logging & Feedback

Log format:
`[ISO_TIMESTAMP] message`

Always:
- Clear log when a major new operation starts
- Append each sub-result line
- Auto-scroll log container to bottom

---

## 10. Performance Considerations

| Scenario | Strategy |
|----------|----------|
| Thousands of books | Add server-side `?limit=500` or implement incremental loading button |
| Large mapping table | Provide `?limit=` & future `?offset=` pagination |
| Many POSTs (N×M)    | Later introduce a bulk POST endpoint `{ mappings: [ {user_id, book_id}, ... ] }` |
| UI sluggishness     | Defer render using `DocumentFragment` and single append |

---

## 11. Error Handling Guidelines

- Return 400 with `{"error": "<message>"}` on validation failure.
- Return 403 on admin check failure.
- Never propagate raw tracebacks to the client (log internally instead).
- Use try/except around external DB (metadata.db) lookups; degrade gracefully.

---

## 12. Testing Checklist

| Test Case | Result |
|-----------|--------|
| Non-admin user requests endpoint | 403 |
| Admin loads page | 200 + UI renders |
| Add mapping existing | Status: exists |
| Add mapping new | Status: added |
| Delete mapping | Status: deleted |
| Upsert with missing IDs | Removed count > 0 |
| Upsert no change | added=0 removed=0 |
| Large list load with limit | Respected |
| metadata.db temporarily missing | Books list empty; no crash |

---

## 13. Example Minimal Route (Pseudo)

```
@bp.route("/admin/all_items", methods=["GET"])
def admin_all_items():
    auth = _require_admin()
    if auth is not True:
        return auth
    limit = request.args.get("limit", type=int)
    items = services.list_items(limit=limit)
    return jsonify({"items": items, "count": len(items)})
```

---

## 14. Example Services Snippet (Pseudo)

```
def list_items(limit=None):
    with plugin_session() as s:
        q = s.execute(select(ItemModel.id, ItemModel.name).order_by(ItemModel.id.asc()))
        rows = q.fetchall()
    data = [{"id": r.id, "name": r.name} for r in rows]
    if limit:
        data = data[:limit]
    return data
```

---

## 15. Example Template Snippet (Minimal Layout)

```
{% extends "layout.html" %}
{% set title = 'Feature Admin' %}
{% block body %}
<div class="panel panel-default">
  <div class="panel-heading"><h3 class="panel-title">Feature Admin</h3></div>
  <div class="panel-body">
    <div class="row">
      <div class="col-sm-4">
        <input id="filter-a" class="form-control input-sm" placeholder="Filter A">
        <div id="list-a" style="max-height:220px;overflow:auto;"></div>
      </div>
      <div class="col-sm-4">
        <input id="filter-b" class="form-control input-sm" placeholder="Filter B">
        <div id="list-b" style="max-height:220px;overflow:auto;"></div>
      </div>
      <div class="col-sm-4">
        <button id="btn-add" class="btn btn-success btn-sm">Add</button>
        <button id="btn-refresh" class="btn btn-primary btn-sm">Refresh</button>
        <pre id="log" style="margin-top:8px;max-height:180px;overflow:auto;"></pre>
      </div>
    </div>
    <hr>
    <table class="table table-condensed" id="mapping-table">
      <thead><tr><th>A</th><th>B</th><th>Action</th></tr></thead>
      <tbody id="mapping-tbody"></tbody>
    </table>
  </div>
</div>
{% endblock %}
```

---

## 16. Deployment / Integration Steps

1. Create new model (if needed) + migration placeholder.
2. Add service functions.
3. Add API routes (admin-protected).
4. Add template file extending `layout.html`.
5. Register blueprint (already done globally in plugin init).
6. Reload container (or rely on autoreload if debug).
7. Functional test with sample data.
8. Record feature in README / CHANGELOG.

---

## 17. Rollback Plan

- Keep changes isolated (new file set).
- If feature misbehaves, disable by removing from `CALIBRE_WEB_PLUGINS` list or comment out registration function.
- Database artifacts: If a new table was added and must be removed, drop via manual SQL or implement a reversible migration.

---

## 18. Common Pitfalls

| Issue | Cause | Fix |
|-------|-------|-----|
| 403 on admin endpoints | Missing `utils.ensure_admin()` call | Add guard |
| Empty book/user list | metadata.db or user session not ready | Verify core Calibre is configured; reload |
| Slow add loop | Large N×M pair expansion | Implement bulk endpoint later |
| Mixed casing email filter misses | Case-sensitive filter | Lowercase both sides when filtering |
| Template not updating | Debug off with cached template | Enable debug or restart container |

---

## 19. Future Enhancements (Optional)

- Client-side pagination / infinite scroll.
- Bulk endpoint for multi-insert / multi-delete.
- Column sorting + search across joined metadata.
- Export CSV of mappings.
- Audit logging (append-only table).
- Permission tiers (not just admin).

---

## 20. Quick Start Checklist (Copy/Paste)

```
[ ] Define models_<feature>.py (if schema needed)
[ ] Add services_<feature>.py with CRUD + list
[ ] Create routes_<feature>.py (admin endpoints)
[ ] Reference routes_<feature>.register() in api/__init__.py
[ ] Build <feature>_admin.html template
[ ] Test endpoints with curl/Postman
[ ] Verify UI loads & maps add/delete actions
[ ] Add instructions entry + README note
[ ] Commit & tag
```

---

## 21. FAQ

**Q: Should I reuse `users_books` DB session code?**  
Yes—use the same `plugin_session()` helper for all plugin-local tables to avoid duplicate engines.

**Q: Can I join directly against Calibre core tables?**  
Prefer reading via the existing Calibre DB (user / metadata) context or raw `sqlite3` for metadata; avoid writing to core tables.

**Q: How do I add pagination later?**  
Add `?limit=&offset=` params; apply slicing before mapping expansion; return `next_offset` when more rows remain.

---

## 22. Versioning Guidance

- Increment plugin version on each new admin page addition.
- Document endpoints in the project README’s API reference section.

---

## 23. Security Reminder

- Never trust IDs from the client—always type-check & convert.
- Do not echo raw user input in HTML without escaping.
- Keep admin-only logic server-side; do not rely on hiding buttons.

---

## 24. Change Log Stub (for reuse)

```
### Added
- <feature>: Admin UI with selectable users/books and mapping management.
- Endpoints: /admin/all_users, /admin/all_books, /admin/mappings_full
```

---

## 25. Ready-Made TODO Template

```
TODO (<feature>):
  [ ] Define model
  [ ] Write services
  [ ] Implement routes (GET list, POST add, DELETE, optional upsert)
  [ ] Build template
  [ ] Add JS: load lists, filter, selection, map apply, delete
  [ ] Add log output
  [ ] Test with sample data
  [ ] Document endpoints
  [ ] Review security (ensure admin checks)
```

---

## 26. Final Advice

Ship minimal first:
- Lists + Add + Delete + Log.
Iterate later with pagination, advanced filters, and search.

Repeatable pattern = predictable maintenance.

---

## 27. Machine Prompt Snippets (AI / Copilot Seed)

Use these copy/paste prompt fragments inside new files to guide AI assistants (e.g. Copilot) so they reproduce the established patterns safely and consistently.

### 27.1 Route File Seed

```
"""
routes_<feature>.py

Admin endpoints for <feature> mapping (left ↔ right entities).

Endpoints:
  GET    /plugin/<plugin>/admin/<feature>/all_left
  GET    /plugin/<plugin>/admin/<feature>/all_right
  GET    /plugin/<plugin>/admin/<feature>/mappings
  POST   /plugin/<plugin>/admin/<feature>/<left_id>/add   { "right_id": int }
  DELETE /plugin/<plugin>/admin/<feature>/<left_id>/<right_id>

Constraints:
  - Admin only (use utils.ensure_admin()).
  - All DB via plugin_session().
  - Return consistent JSON: list -> {items:[]}, mappings -> {mappings:[], count:n}, mutating -> {status:"...", ...}
"""
```

### 27.2 Service File Seed

```
"""
services_<feature>.py

Business logic for <feature> mappings.
Keep routes thin; expose:
  list_left(limit=None)
  list_right(limit=None)
  list_mappings(limit=None)
  add_mapping(left_id,right_id) -> bool
  remove_mapping(left_id,right_id) -> bool
All DB access through plugin_session().
"""
```

### 27.3 Template Seed

```
{% extends "layout.html" %}
{% set title = '<Feature> Admin' %}
{% block body %}
<div class="panel panel-default">
  <div class="panel-heading"><h3 class="panel-title">{{ title }}</h3></div>
  <div class="panel-body">
    <p class="text-muted">Manage <feature> mappings: select left + right, then add.</p>
    <div class="row">
      <div class="col-sm-4">
        <input id="filter-left" class="form-control input-sm" placeholder="Filter left">
        <div id="left-box" style="max-height:220px;overflow:auto;margin-top:6px;"></div>
        <div style="margin-top:6px;">
          <button id="left-reload" class="btn btn-default btn-xs">Reload</button>
          <button id="left-all" class="btn btn-default btn-xs">All</button>
          <button id="left-clear" class="btn btn-default btn-xs">Clear</button>
        </div>
      </div>
      <div class="col-sm-4">
        <input id="filter-right" class="form-control input-sm" placeholder="Filter right">
        <div id="right-box" style="max-height:220px;overflow:auto;margin-top:6px;"></div>
        <div style="margin-top:6px;">
          <button id="right-reload" class="btn btn-default btn-xs">Reload</button>
          <button id="right-all" class="btn btn-default btn-xs">All</button>
          <button id="right-clear" class="btn btn-default btn-xs">Clear</button>
        </div>
      </div>
      <div class="col-sm-4">
        <button id="add-mappings" class="btn btn-success btn-sm">Add Selected</button>
        <button id="refresh-mappings" class="btn btn-primary btn-sm">Refresh Mappings</button>
        <pre id="log" style="margin-top:8px;max-height:200px;overflow:auto;background:#222;color:#eee;padding:6px;font-size:11px;"></pre>
      </div>
    </div>
    <hr>
    <h4>Mappings</h4>
    <table class="table table-condensed table-striped">
      <thead><tr><th>Left</th><th>Right</th><th>Delete</th></tr></thead>
      <tbody id="mappings-tbody"></tbody>
    </table>
  </div>
</div>
{% endblock %}
```

### 27.4 Copilot Micro Prompts

Embed one of these at the top of a new file to steer generation:

```
# GOAL: Implement admin CRUD endpoints for <feature> similar to users_books.
# MUST: admin guard, plugin_session, JSON responses (items/mappings/status).
# RETURN SHAPES:
#   list -> { "items": [...] }
#   mappings -> { "mappings": [...], "count": N }
#   add/delete -> { "status": "...", "left_id": X, "right_id": Y }
```

```
# SERVICE GOAL: Provide list_left, list_right, list_mappings, add_mapping, remove_mapping.
# All DB access via plugin_session(); no Flask imports.
```

### 27.5 Escaping / Safety Prompt

```
# SAFETY:
# - Validate ints (reject non-positive or non-int)
# - Admin check first; return 403 JSON on failure
# - Never trust client-supplied email/title; escape in template
# - Return deterministic keys in JSON
```

### 27.6 Bulk Endpoint Prompt (Optional Future)

```
# Add bulk endpoint:
# POST /admin/<feature>/bulk_add { "pairs": [ { "left_id": int, "right_id": int }, ... ] }
# Return: { requested: N, added: N_added, existing: N_existing, errors: [] }
```

---

## 28. Micro Seed Checklist

A fast copy/paste list to drop into an empty file for maximal AI leverage:

```
# FEATURE: <feature>
# ENTITIES: left=<describe>, right=<describe>
# ENDPOINTS:
#   GET  all_left
#   GET  all_right
#   GET  mappings
#   POST <left_id>/add { right_id }
#   DELETE <left_id>/<right_id>
# RULES:
#   - Admin only
#   - Use plugin_session()
#   - JSON shapes standardized
# TODO:
#   [ ] Implement services
#   [ ] Implement routes
#   [ ] Build template
#   [ ] Test add/delete
#   [ ] Add log output
#   [ ] Document in README
```

---

(End of template)