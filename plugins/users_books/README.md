# users_books (Minimal)

Minimal retained functionality per cleanup request:

1. Separate SQLite database storing (user_id, book_id) allow-list mappings.
2. Admin JSON endpoints to view and modify mappings.
3. Simple HTML admin UI at `/plugin/users_books/admin/ui` powered by those JSON endpoints.
4. Automatic navigation button injection ("ebooks.lv") for admins (appears after the standard Admin link).

Removed: user self-service routes, metrics, purchase webhook, filtering hook, caching, debug endpoints, and all ancillary analytics.

## Admin Endpoints

Base prefix: `/plugin/users_books`

```
GET    /admin/<user_id>/filters
POST   /admin/<user_id>/filters            { "book_id": <int> }
DELETE /admin/<user_id>/filters/<book_id>
POST   /admin/<user_id>/filters/bulk       { "book_ids": [int, ...] }
PUT    /admin/<user_id>/filters/upsert     { "book_ids": [int, ...] }
GET    /admin/ui                          (HTML management page)
```

All endpoints require an authenticated admin session (Calibre-Web `is_admin` / role check).

## Database

Single table `users_books`:
```
id INTEGER PK AUTOINCREMENT
user_id INTEGER NOT NULL
book_id INTEGER NOT NULL
UNIQUE(user_id, book_id)
INDEX(user_id, book_id)
```

Path defaults to `users_books.db` (relocates under `CALIBRE_DBPATH` when that env var is set).

## Navigation Injection

Two-layer strategy (template loader + after_request HTML fallback) inserts a list item with label `ebooks.lv`. Only visible to admin users. No environment variables control this; if upstream layout changes, the injection safely no-ops.

## Logging

Environment variable `USERS_BOOKS_LOG_LEVEL` (default INFO) controls verbosity. Logs are prefixed with `[users_books]`.

## Initialization

```
import users_books
users_books.init_app(app)
```

This will: configure logging, initialize the DB schema if needed, register the blueprint, and set up nav injection.

---
Further features (filtering, metrics, webhook) intentionally removed for lean runtime. Reintroduce them by restoring earlier commits if required.

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
