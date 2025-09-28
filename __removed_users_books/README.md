# users_books Plugin (Advanced User Book Visibility Filtering)

> Updated: This plugin now implements robust per-user allow‑list filtering of Calibre-Web books, an admin bypass, an isolated SQLite database (`user_filters.db` by default), a SQLAlchemy `before_compile` hook to transparently constrain queries, REST endpoints for users/admins to manage allowed book mappings, request‑scoped caching, optional metrics, and a purchase webhook that resolves users by email without storing emails in the plugin database (no separate email entitlement table).

## What Changed (Advanced Mode)
- Transparent filtering: Non‑admin users only see books whose IDs are in their personal allow list.
- Admin bypass: Sessions with `is_admin=True` are never filtered.
- Independent storage: Plugin maintains its own SQLite file so upgrades to Calibre-Web schema are isolated from plugin data.
- Query hook: A safe `before_compile` hook injects `Books.id IN (...)` only when the query actually involves the `Books` table.
- Request cache: Minimizes repeated DB lookups per request.
- Management API:
  - User endpoints to list/add/remove their own allowed book IDs.
  - Admin endpoints to manage any user’s list.
  - Optional `/metrics` endpoint (admin only) when enabled.
- Environment driven behavior (paths, limits, metrics, strict empty enforcement).
- Defensive fallbacks if allow list is empty or too large.

## Environment Variables
| Variable | Default | Purpose |
|----------|---------|---------|
| USERS_BOOKS_DB_PATH | user_filters.db | SQLite DB file path for mappings |
| USERS_BOOKS_MAX_IDS_IN_CLAUSE | 500 | Safety cap on how many IDs go into an IN(...) clause |
| USERS_BOOKS_ENABLE_METRICS | (unset) | Enable `/plugin/users_books/metrics` when `1/true` |
| USERS_BOOKS_LOG_LEVEL | INFO | Plugin logger level |
| USERS_BOOKS_ENFORCE_EMPTY | true | If true, empty allow list -> zero results; else no filter |
| (nav link) | - | Nav link injection now unconditional; no env vars control it |

## REST Endpoints Summary
(Per-user allow‑list only; no email entitlement staging table. The purchase webhook immediately resolves the user by email in Calibre‑Web. If the user does not yet exist the caller must retry later.)

User (must have valid session with `user_id`):
- GET  `/plugin/users_books/health`
- GET  `/plugin/users_books/filters`
- POST `/plugin/users_books/filters` JSON: `{ "book_id": <int> }`
- DELETE `/plugin/users_books/filters/<book_id>`

Admin (session `is_admin=True`):
- GET    `/plugin/users_books/admin/<user_id>/filters`
- POST   `/plugin/users_books/admin/<user_id>/filters` JSON: `{ "book_id": <int> }`
- DELETE `/plugin/users_books/admin/<user_id>/filters/<book_id>`
- GET    `/plugin/users_books/metrics` (only if metrics enabled)

### Webhook Endpoint (Purchase Integration)

Purpose:
Grant a user access to a purchased book by email without persisting the email in the plugin DB (email is looked up in Calibre‑Web’s native user table).

Endpoint:
- POST `/plugin/users_books/webhook/purchase`

Headers:
- `Content-Type: application/json`
- `X-API-Key: <USERS_BOOKS_WEBHOOK_API_KEY>`

Body:
```
{
  "email": "buyer@example.com",
  "book_id": 123
}
```

Responses:
- 200 `{ "status": "created", "user_id": <int>, "book_id": <int> }` (mapping added)
- 200 `{ "status": "exists", ... }` (idempotent)
- 404 `{ "status": "user_not_found", "email": "...", "book_id": ... }`
- 400 error JSON for malformed input
- 401 unauthorized (bad / missing API key)
- 403 disabled if `USERS_BOOKS_WEBHOOK_API_KEY` not set

Environment:
- `USERS_BOOKS_WEBHOOK_API_KEY` (required to enable)
- (Optional) `USERS_BOOKS_SESSION_EMAIL_KEY` (defaults to `email`) used only for potential future UI logic—NOT for filtering.

Rationale (No Email Table):
- Simpler schema: only `user_filters`
- No duplicated PII
- Caller is responsible for retrying if the user account isn’t created yet
- Easy to extend later with a staging table if pre‑provisioning becomes necessary

Failure / Retry Strategy:
If you receive `user_not_found`, delay and retry after the user registers. This keeps plugin logic minimal.

Security Notes:
- Keep the API key secret (mount as env variable, do not bake into image)
- Consider adding IP allow‑listing or HMAC signing later
- Rate limit upstream (reverse proxy) if exposed publicly

User (must have valid session with `user_id`):
- GET  `/plugin/users_books/health`
- GET  `/plugin/users_books/filters`
- POST `/plugin/users_books/filters` JSON: `{ "book_id": <int> }`
- DELETE `/plugin/users_books/filters/<book_id>`

Admin (session `is_admin=True`):
- GET    `/plugin/users_books/admin/<user_id>/filters`
- POST   `/plugin/users_books/admin/<user_id>/filters` JSON: `{ "book_id": <int> }`
- DELETE `/plugin/users_books/admin/<user_id>/filters/<book_id>`
- GET    `/plugin/users_books/metrics` (only if metrics enabled)

## Filtering Logic (Detailed)
1. On initialization, the plugin registers a SQLAlchemy `before_compile` hook on `Select`.
2. For each compiled statement inside a request context:
   - Skips if user not logged in or is admin.
   - Checks if the `Books` table participates in the query.
   - Fetches (and caches) the user’s allowed book IDs.
   - If empty and `USERS_BOOKS_ENFORCE_EMPTY=true`, injects a `FALSE` predicate (return no rows).
   - Otherwise injects `Books.id IN (<allowed_ids>)`, respecting the `USERS_BOOKS_MAX_IDS_IN_CLAUSE` ceiling.
3. If the number of IDs exceeds the cap, the plugin logs a warning and skips filtering (fails open) to avoid parameter explosion.

## Caching
- A per-request dictionary stored on `flask.g` caches the list of allowed IDs for the current user.
- Cache invalidated immediately upon any change (add/remove) through the API endpoints.

## Metrics (Optional)
`/plugin/users_books/metrics` (admin only, enabled via `USERS_BOOKS_ENABLE_METRICS`) returns:
```
{
  "plugin": "users_books",
  "total_mappings": <int>,
  "distinct_users": <int>,
  "distinct_books": <int>
}
```

## Operational Considerations
| Concern | Strategy |
|---------|----------|
| Large allow lists | Raise `USERS_BOOKS_MAX_IDS_IN_CLAUSE` or move to join/table-based approach later |
| Concurrency | SQLite is sufficient for light writes; migrate to another engine if needed |
| Auditing | Add trigger logic or separate audit table (future) |
| Performance | Add pagination endpoints; consider caching layer if lists grow large |
| Security | Rely on Calibre-Web session; ensure session keys (`user_id`, `is_admin`) are reliable |

## Extension Ideas
- Bulk import endpoint for admin (e.g., POST a CSV/JSON of book IDs).
- Group or role-based lists (e.g., group -> set of books; user inherits).
- Deny-list mode (inverse logic) toggle.
- UI integration: Admin panel page to manage user filter mappings visually.
- Automated synchronization with an external entitlement system.
- Enhanced UI integration via a dedicated Jinja macro instead of string injection (future once upstream adds plugin hook point).

### Navigation Link Injection

The plugin inserts a "Users Books" nav link (admins only) immediately after the existing Admin link without modifying upstream files.

Mechanics (two-layer reliability):
1. Template loader wrapper patches `layout.html` source in-memory on first load, adding a Jinja-guarded snippet right after the Admin `<li>`.
2. A minimal `after_request` fallback injects at response time only if (rarely) the link is still missing for an admin user.

There are no environment variables controlling this feature (kept intentionally simple). If upstream removes the Admin anchor (`id="top_admin"`), the injection becomes a harmless no-op.

---
(Original template documentation follows below; retained for historical context.)

A sample / template Calibre-Web plugin that demonstrates how to extend the upstream application with user‑centric book features and HTTP endpoints.

This plugin is intentionally minimal so you can evolve it into something production‑ready: add real data access, permissions, templates, caching, background jobs, etc.

---

## Goals

- Provide a clear pattern for plugin initialization (`init_app(app)`).
- Show how to expose simple JSON endpoints.
- Serve as a base for future plugins under `plugins/`.
- Encourage clean separation between:
  - Bootstrap / entrypoint logic (`entrypoint/entrypoint_mainwrap.py`)
  - Upstream code (`calibre-web/` submodule)
  - Plugin extensions (`plugins/<name>/`)

---

## Repository Layout (Relevant Parts)

```
calibre-web-server/
  calibre-web/                 # Upstream (git submodule)
  entrypoint/
    entrypoint_mainwrap.py     # Intercepts upstream main(), then loads plugins & starts the server
  plugins/
    users_books/
      users_books/
        __init__.py            # Plugin root (exports init_app)
      README.md                # This file
```

Inside `users_books/users_books/__init__.py` you will find:
- Route `/plugin/users_books/health`
- Route `/plugin/users_books/example_list`
- A single exported function: `init_app(app)`

---

## How the Plugin Is Loaded

1. The container (or local Python process) executes `entrypoint/entrypoint_mainwrap.py`.
2. The interception entrypoint:
   - Adds `calibre-web/` (upstream) to `sys.path`.
   - Scans the `plugins/` directory, adjusting `sys.path` for plugin import.
   - Reads `CALIBRE_WEB_PLUGINS` (comma-separated) and imports each listed plugin.
   - Calls each plugin’s `init_app(app)` before the server starts.
3. The Flask/Calibre-Web app runs with all registered routes and hooks active.

---

## Configuration / Environment Variables

(Defined or interpreted externally, but you may read them inside the plugin.)

Suggested (none strictly required yet):
- `USERS_BOOKS_ENABLE_STATS` (boolean, future feature)
- `USERS_BOOKS_PAGE_SIZE` (default could be 50)
- `USERS_BOOKS_LOG_LEVEL` (e.g., `INFO`, `DEBUG`)

Add logic in `init_app` later as features grow.

---

## Adding Real Logic

Potential next steps:
1. Data Access:
   - Integrate with Calibre-Web’s ORM/data layer (inspect upstream code for existing models).
   - Provide endpoints filtered by current user.
2. Authentication / Authorization:
   - Reuse Calibre-Web’s session / login system.
   - Restrict endpoints to authenticated users only (Flask decorators or upstream utilities).
3. Templates:
   - Add a `templates/` directory inside `users_books/`.
   - Register blueprint with `template_folder="templates"` and supply Jinja templates.
4. Services / Layering:
   - Add `services.py` for business logic (avoid large route functions).
   - Add `repository.py` if you introduce data abstraction wrappers.

---

## Example Blueprint (Future Pattern)

(For planning only—NOT yet in code.)

```
users_books/
  users_books/
    __init__.py
    blueprint.py
    services.py
    templates/
      users_books/
        list.html
```

Then in `__init__.py`:

```
from .blueprint import bp as users_books_bp
app.register_blueprint(users_books_bp, url_prefix="/plugin/users_books")
```

---

## Development Workflow

1. Ensure submodule is initialized:
   ```
   git submodule update --init --recursive
   ```
2. Build and run:
   ```
   docker compose build
   docker compose up -d
   ```
3. Hit health endpoint:
   - http://localhost:8083/plugin/users_books/health
4. Live Editing:
   - Because `plugins/` is mounted as a volume (see `compose.yaml`), changes auto-reload only if Flask debug mode is enabled.
   - To enable debugging (dev only):
     ```
     export CALIBRE_WEB_DEBUG=1
     docker compose up -d --build
     ```

---

## Enabling Multiple Plugins

Set (example):
```
CALIBRE_WEB_PLUGINS=users_books,another_plugin,third_plugin
```

Each must:
- Be discoverable via `sys.path` (the repository layout pattern matches `plugins/<dir>/<package>/__init__.py`).
- Export `init_app(app)`.

---

## Testing (Recommended Approach)

1. Add a `tests/` directory at the repo root:
   ```
   tests/
     test_users_books_health.py
   ```
2. Example (pseudo):
   ```
   from cps import __init__ as cps_init
   from users_books import init_app
   def test_health():
       app = cps_init.app
       init_app(app)
       client = app.test_client()
       r = client.get("/plugin/users_books/health")
       assert r.status_code == 200
       assert r.json.get("plugin") == "users_books"
   ```
3. Run inside container or local venv with `pytest`.

---

## Logging

Currently uses simple `print(...)` statements to standard output so Docker logs capture them. For more sophisticated logging:
- Import `logging`
- Configure a logger in `init_app`
- Follow a prefix convention: `[users_books] ...`

---

## Versioning

`PLUGIN_VERSION` constant (initially `0.1.0`) lives in `__init__.py`.

Recommended semantic versioning rules:
- Patch (`0.1.x`): Bug fixes / internal refactors
- Minor (`0.x+1.0`): New endpoints or non-breaking changes
- Major (`1.0.0`): Breaking API/path/config changes

---

## Security Considerations (Future)

- Input validation on any new endpoints accepting query/body parameters.
- Rate limiting if you expose expensive queries.
- Respect Calibre-Web permissions (e.g., restrict user-private data).
- Avoid direct file system manipulations without sanitation.

---

## Performance Ideas

- Add caching for frequently accessed lists (`Flask-Caching` or upstream support).
- Paginate large result sets (`?page=2&page_size=50`).
- Consider asynchronous tasks for long-running operations.

---

## Roadmap / Ideas

| Feature | Description | Priority |
|---------|-------------|----------|
| Real user book listing | Query library per authenticated user | High |
| Pagination & filters | Query params: status, tags, read-state | High |
| Templates & UI page | Render user bookshelf page | Medium |
| Stats endpoint | Aggregations: counts by author/genre | Medium |
| Export feature | Download CSV/JSON of user’s books | Low |
| Caching layer | Speed up repeated queries | Low |
| Admin config UI | Toggle plugin features | Low |

---

## Uninstallation / Removal

Simply:
1. Remove `users_books` from `CALIBRE_WEB_PLUGINS`.
2. (Optionally) Delete `plugins/users_books/`.
3. Rebuild the image if you baked plugins into the image.

---

## License

(Choose one—e.g., MIT, Apache-2.0, GPL-3.0—and state it both here and at the root if different from the main project.)

Example placeholder:

```
SPDX-License-Identifier: MIT
Copyright (c) YEAR Your Name
```

---

## Quick Reference

| Action | Command / URL |
|--------|---------------|
| Health check | GET /plugin/users_books/health |
| Example list | GET /plugin/users_books/example_list |
| Enable debug | `CALIBRE_WEB_DEBUG=1` |
| Multiple plugins | `CALIBRE_WEB_PLUGINS=users_books,another` |
| Rebuild container | `docker compose build && docker compose up -d` |

---

## FAQ

Q: Why is the import name just `users_books`?  
A: The entrypoint adds each `plugins/<dir>` path to `sys.path`; the inner package shares its directory name, keeping import statements short.

Q: Can I turn this into a pip package?  
A: Yes—add a `pyproject.toml` inside `users_books/` (sibling to the package) and build/publish. Then install it in the Docker build instead of mounting.

Q: How do I disable it temporarily?  
A: Remove it from `CALIBRE_WEB_PLUGINS` or set that variable empty.

---

## Contributing

1. Open a feature branch.
2. Add / adjust routes or services.
3. Include or update tests.
4. Update this README (endpoints, config keys, version).
5. Open PR; ensure submodule state is not unintentionally changed.

---

## Changelog (Start Here)

- 0.1.0
  - Initial skeleton with health + example list endpoints.
  - Basic initialization pattern documented.

---

If you want help scaffolding a second plugin or converting this into a packaged distribution, let me know and we can generate that next.
