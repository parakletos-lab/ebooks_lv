# calibre-web-server

Custom Calibre-Web deployment wrapper that:
- Keeps the upstream Calibre-Web code as a git submodule (no direct edits).
- Inlines all custom functionality directly into a first‑party application layer (`app/`).
- Uses a minimal interception entrypoint (`entrypoint/entrypoint_mainwrap.py`) to perform environment bootstrap and then hand off to upstream.
- Ships with a Docker + Compose workflow for predictable deployments and live development.
- Encourages clear service/data separation for safe upstream upgrades.

---

## Key Features

- Upstream isolation: submodule pins an exact Calibre-Web version/commit.
- First‑party extension layer: all custom routes, services, models under `app/` (no dynamic plugin loading).
- Docker image with layered caching and optional healthcheck.
- Live development via bind-mounted volumes (config, data, app code).
- Clear boundaries for safe upstream upgrades.

---

## Directory Structure

```
calibre-web-server/
  calibre-web/                 # Upstream Calibre-Web (git submodule)
  app/                         # First‑party extensions (models/services/routes/utils)
  entrypoint/
    entrypoint_mainwrap.py     # Intercepts upstream startup for env/setup tasks
  config/                      # (Created at runtime / via volume) Calibre-Web config
  var/
    data/                      # (Created at runtime / via volume) Library / persistent data
  Dockerfile
  compose.yaml
  README.md
```

Notes:
- `config/` and `var/data/` may not exist until first run (or create manually).
- All customization lives under `app/`; no plugin loader remains.

---

## Application Bootstrap Model

`entrypoint/entrypoint_mainwrap.py` performs a minimal wrapper around upstream startup:
1. Ensures the working directory and PYTHONPATH include upstream & `app/`.
2. (Optional) Runs seeding if `RUN_SEED=1` (establishes core settings rows / keys).
3. Invokes upstream Calibre-Web creation logic.
4. Imports and registers internal `app.` routes/services (import side‑effects only; no dynamic enumeration).

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

4. View logs:
   ```
   docker compose logs -f
   ```

Stop services:
```
docker compose down
```

---

## Pre-Seeding the Settings Database

Why pre-seed?
- Deterministic startup (no AttributeError during early `create_app()` phases)
- Ensures encryption key `.key`, `app.db` (settings) exist
- Idempotent: safe to re-run any time

What it does:
1. Creates (or confirms) the config directory (`CALIBRE_DBPATH` or default).
2. Generates the Calibre-Web encryption key if missing.
3. Creates `app.db` and inserts the default settings row if absent.
4. Ensures Flask session key row exists.

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
[SEED] Calibre-Web pre-seed summary:
{
  "calibre": {
    "config_dir": "/app/config",
    "settings_path": "/app/config/app.db",
    "settings_row_present": true,
    "encryption_key_present": true
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

Recovery / Re-seed:
If you delete `config/` contents, just re-run the seed script; existing data (if stored elsewhere) is untouched unless you remove it.

---

## Running Without Compose (Raw Docker)

```
docker build -t calibre-web-server .
docker run -d \
  -p 8083:8083 \
  -v "$PWD/config:/app/config" \
  -v "$PWD/var/data:/app/data" \
  calibre-web-server
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| CALIBRE_WEB_HOST | `0.0.0.0` | Bind interface |
| CALIBRE_WEB_PORT | `8083` | HTTP port |
| CALIBRE_WEB_DEBUG | (unset) | `1`, `true` enables Flask debug (development only) |
| TZ | System dependent | Timezone inside container |
| USERS_BOOKS_DB_PATH | (legacy) | Only used for migrating historical plugin DB if present |

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

## Extending Functionality

Add new models/services/routes directly under the `app/` package following existing patterns. Avoid dynamic import tricks; keep registration explicit for clarity and upgrade safety.

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

With volumes mounted, code changes are reflected immediately—Flask auto-reload only when debug is enabled.

---

## Testing (Recommended Pattern)

Add a root-level `tests/` directory:
```
tests/
  test_app_root.py
```

Example (pseudo):
```python
from cps import __init__ as cps_init  # upstream app

def test_root():
    app = cps_init.app
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
```

Run inside a virtual environment or in a dev container with `pytest`.

---

## Security Considerations

- Keep submodule updated for upstream security fixes.
- Only enable debug in development.
- Validate/authorize all new endpoints involving user-specific data.
- Avoid writing outside `/app/config` and `/app/data` unless intentional.
- Consider running behind an HTTPS terminator (reverse proxy / ingress).

---

## Troubleshooting

| Symptom | Possible Cause | Fix |
|---------|----------------|-----|
| `ModuleNotFoundError: cps` | Submodule not initialized | Run submodule init/update |
| No route found | Registration error | Confirm import side-effects executed |
| Changes not reflecting | Not using debug / stale container | Rebuild or set `CALIBRE_WEB_DEBUG=1` |
| Port already in use | Host port 8083 occupied | Change host mapping in compose |

---

## Roadmap Ideas

| Item | Description | Priority |
|------|-------------|----------|
| Add CI workflow | Lint + test on PRs | High |
| Add test suite for app layer | Prevent regressions on upgrades | High |
| Improve service layer docs | Clarify extension points | Medium |
| Multi-stage production image hardening | Slim runtime size | Medium |
| Documentation site | Publish architecture guide | Low |
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
| Upgrade upstream | `git submodule update --remote calibre-web` |
| Seed settings | Run seed script (one-off container) |

---

Happy hacking—extend responsibly and keep upstream clean.