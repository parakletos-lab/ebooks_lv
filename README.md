# calibre-web-server

Custom Calibre-Web deployment wrapper that:
- Keeps the upstream Calibre-Web code as a git submodule (no direct edits).
- Provides a structured plugin system (`plugins/`), starting with `users_books`.
- Uses an interception entrypoint (`entrypoint/entrypoint_mainwrap.py`) that runs upstream initialization and then loads plugins.
- Ships with a Docker + Compose workflow for predictable deployments and live development.
- Encourages clean separation of concerns and safe upstream upgrades.

---

## Key Features

- Upstream isolation: submodule pins an exact Calibre-Web version/commit.
- Pluggable architecture: load one or more plugins via environment variable.
- Simple plugin contract: each plugin exports `init_app(app)`.
- Docker image with layered caching and optional healthcheck.
- Live development via bind-mounted volumes (config, data, plugins).
- Extensible foundation for future customizations (more plugins, tests, CI).

---

## Directory Structure

```
calibre-web-server/
  calibre-web/                 # Upstream Calibre-Web (git submodule)
  entrypoint/
    entrypoint_mainwrap.py     # Intercepts upstream main(), injects plugins, then starts server
  plugins/
    users_books/
      users_books/             # Python package (import name: users_books)
        __init__.py
      README.md
  config/                      # (Created at runtime / via volume) Calibre-Web config
  var/
    data/                      # (Created at runtime / via volume) Library / persistent data
  Dockerfile
  compose.yaml
  README.md
```

Notes:
- `config/` and `var/data/` may not exist until you first run the container (or create them manually).
- `users_books` plugin contains placeholder routes & initialization logic.
- Additional plugins follow the same nesting pattern: `plugins/<plugin_dir>/<plugin_package>/__init__.py`.

---

## Plugin Loading Model

1. `entrypoint/entrypoint_mainwrap.py` intercepts `web_server.start()` & `sys.exit`, then calls `cps.main.main()` for native initialization:
   - Ensures `calibre-web/` and plugin directories are on `PYTHONPATH`
   - (Optional) Runs seeding if `RUN_SEED=1`
2. Loads plugins from `CALIBRE_WEB_PLUGINS` and then starts the Flask dev server (swap to gunicorn for production).
3. For each name, it imports the module and calls `init_app(app)`.
4. The Flask/Calibre-Web app then serves with all plugin routes and hooks available.

Example:
```
CALIBRE_WEB_PLUGINS=users_books,another_plugin
```

Each plugin must:
- Be importable (path on `sys.path`).
- Export a callable `init_app(app)`.

---

## Quick Start (Docker Compose)

Prerequisites: Docker + Docker Compose plugin.

1. Initialize the submodule (first clone only):
   ```
   git submodule update --init --recursive
   ```

2. Build and start:
   ```
   docker compose build
   docker compose up -d
   ```

3. Access the app:
   - Calibre-Web (default): http://localhost:8083
   - Plugin health endpoint (example): http://localhost:8083/plugin/users_books/health

4. View logs:
   ```
   docker compose logs -f
   ```

Stop services:
```
docker compose down
```

---
## Pre-Seeding the Settings Database (Option 5)

To avoid first‑run initialization edge cases (missing default `_Settings` row, schedule attribute errors, etc.) you can pre‑seed the Calibre‑Web settings DB and the `users_books` plugin DB before the main server starts.  
A helper script `entrypoint/seed_settings.py` is included for this purpose.

Why pre-seed?
- Deterministic startup (no AttributeError during early `create_app()` phases)
- Ensures encryption key `.key`, `app.db` (settings), Flask session key, and plugin DB exist
- Idempotent: safe to re-run any time

What it does:
1. Creates (or confirms) the config directory (`CALIBRE_DBPATH` or default).
2. Generates the Calibre-Web encryption key if missing.
3. Creates `app.db` and inserts the default settings row if absent.
4. Ensures Flask session key row exists.
5. If the `users_books` plugin is present, initializes its SQLite DB (respecting `USERS_BOOKS_DB_PATH`, colocated under `CALIBRE_DBPATH` when relative).

Usage (with Docker Compose):
```
# 1. Make sure submodule is initialized
git submodule update --init --recursive

# 2. (Optional) create host directories with correct permissions
mkdir -p config var/data

# 3. Run the seeding script in a one-off container
docker compose run --rm calibre-web-server python entrypoint/seed_settings.py
```

Example output (truncated):
```
[SEED] Calibre-Web + plugin pre-seed summary:
{
  "calibre": {
    "config_dir": "/app/config",
    "settings_path": "/app/config/app.db",
    "settings_row_present": true,
    "encryption_key_present": true
  },
  "users_books": {
    "plugin_present": true,
    "db_path": "/app/config/users_books.db",
    "initialized": true,
    "error": null
  }
}
[SEED] Done.
```

Then start normally:
```
docker compose up -d
```

One-liner (seed + start):
```
docker compose run --rm calibre-web-server python entrypoint/seed_settings.py && \
docker compose up -d
```

Environment variables that affect seeding:
- `CALIBRE_DBPATH` (config directory; also where `app.db` and `.key` live)
- `USERS_BOOKS_DB_PATH` (plugin DB filename/path; if relative, resolved under `CALIBRE_DBPATH`)
- `CALIBRE_WEB_PLUGINS` (must contain `users_books` for its DB to be seeded)

Recovery / Re-seed:
If you delete `config/` contents, just re-run the seed script; existing plugin data (if stored elsewhere) is untouched unless you remove it.

---

## Running Without Compose (Raw Docker)

```
docker build -t calibre-web-server .
docker run -d \
  -p 8083:8083 \
  -e CALIBRE_WEB_PLUGINS=users_books \
  -v "$PWD/config:/app/config" \
  -v "$PWD/var/data:/app/data" \
  -v "$PWD/plugins:/app/plugins" \
  --name calibre-web-server \
  calibre-web-server
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| CALIBRE_WEB_PLUGINS | `users_books` | Comma-separated list of plugin import names |
| CALIBRE_WEB_HOST | `0.0.0.0` | Bind interface |
| CALIBRE_WEB_PORT | `8083` | HTTP port |
| CALIBRE_WEB_DEBUG | (unset) | `1`, `true` enables Flask debug (development only) |
| TZ | System dependent | Timezone inside container |

Plugin-specific variables can be added later (e.g., `USERS_BOOKS_PAGE_SIZE`).

---

## Upgrading Calibre-Web (Submodule)

1. Fetch latest upstream and update:
   ```
   git submodule update --remote calibre-web
   ```
   (Optionally check out a specific tag or commit inside `calibre-web/`.)

2. Commit the new submodule pointer:
   ```
   git add calibre-web
   git commit -m "Upgrade calibre-web to latest upstream"
   ```

3. Rebuild and restart:
   ```
   docker compose build
   docker compose up -d
   ```

Consider scripting this (e.g., `scripts/update_upstream.sh`) for consistency.

---

## Adding a New Plugin

1. Create directories:
   ```
   mkdir -p plugins/my_new_plugin/my_new_plugin
   ```
2. Add `plugins/my_new_plugin/my_new_plugin/__init__.py`:
   ```python
   def init_app(app):
       @app.route("/plugin/my_new_plugin/health")
       def health():
           return {"plugin": "my_new_plugin", "status": "ok"}
   ```
3. Update environment variable:
   ```
   CALIBRE_WEB_PLUGINS=users_books,my_new_plugin
   ```
4. Rebuild or (if mounted) just restart:
   ```
   docker compose restart
   ```

---

## Development Workflow

| Task | Command |
|------|---------|
| Initialize submodule | `git submodule update --init --recursive` |
| Build image | `docker compose build` |
| Start services | `docker compose up -d` |
| Tail logs | `docker compose logs -f` |
| Rebuild after changes | `docker compose up -d --build` |
| Debug mode | Set `CALIBRE_WEB_DEBUG=1` |

With volumes mounted, plugin code changes are reflected immediately—Flask auto-reload only when debug is enabled.

---

## Testing (Recommended Pattern)

Add a root-level `tests/` directory:
```
tests/
  test_users_books_health.py
```

Example (pseudo):
```python
from cps import __init__ as cps_init
from users_books import init_app

def test_health():
    app = cps_init.app
    init_app(app)
    client = app.test_client()
    resp = client.get("/plugin/users_books/health")
    assert resp.status_code == 200
    assert resp.json["plugin"] == "users_books"
```

Run inside a virtual environment or in a dev container with `pytest`.

---

## Security Considerations

- Keep submodule updated for upstream security fixes.
- Only enable debug in development.
- Validate/authorize all new plugin endpoints involving user-specific data.
- Avoid writing outside `/app/config` and `/app/data` unless intentional.
- Consider running behind an HTTPS terminator (reverse proxy / ingress).

---

## Troubleshooting

| Symptom | Possible Cause | Fix |
|---------|----------------|-----|
| `ModuleNotFoundError: cps` | Submodule not initialized | Run submodule init/update |
| Plugin not loading | Wrong name in `CALIBRE_WEB_PLUGINS` | Match import package exactly |
| No route found | `init_app` missing or misnamed | Ensure `def init_app(app):` exists |
| Changes not reflecting | Not using debug / stale container | Rebuild or set `CALIBRE_WEB_DEBUG=1` |
| Port already in use | Host port 8083 occupied | Change host mapping in compose |

---

## Roadmap Ideas

| Item | Description | Priority |
|------|-------------|----------|
| Add CI workflow | Lint + test on PRs | High |
| Add test suite for plugins | Prevent regressions on upgrades | High |
| Additional plugin scaffolding script | Automate new plugin creation | Medium |
| Multi-stage production image hardening | Slim runtime size | Medium |
| Documentation site | Publish plugin dev guide | Low |
| Optional WSGI server (gunicorn) | Production-grade serving | Low |

---

## Contributing

1. Fork / branch.
2. Initialize submodule.
3. Implement changes (avoid editing upstream directly).
4. Add/update tests & docs.
5. Open PR referencing rationale and any upstream version bumps.

---

## License

Specify your chosen license here (e.g., MIT, Apache-2.0, GPL-3.0).  
Example placeholder:

```
SPDX-License-Identifier: MIT
Copyright (c) YEAR <YOUR>
```

---

## Attribution

- Upstream project: https://github.com/janeczku/calibre-web

---

## Quick Reference Table

| Action | Command / URL |
|--------|---------------|
| Build | `docker compose build` |
| Start | `docker compose up -d` |
| Logs | `docker compose logs -f` |
| Health (plugin) | `GET /plugin/users_books/health` |
| Edit plugins | Modify `plugins/<name>/` |
| Upgrade upstream | `git submodule update --remote calibre-web` |
| Set multiple plugins | `CALIBRE_WEB_PLUGINS=users_books,my_new_plugin` |

---

Happy hacking—extend responsibly and keep upstream clean.