# QA (Copilot Agent Context)

This folder is the **stable context** for Copilot agents running repeatable QA/E2E checks against the local dockerized Calibre-Web instance.

## What’s in here
- `credentials.env` – local-only credentials (do not commit secrets)
- `scripts/` – idempotent bootstrap + smoke helpers (meant to run inside the container)
- `e2e/` – human-readable role-based checklists for Anonymous / Non-admin / Admin
- `archive/` – legacy users_books allow-list artifacts kept only for historical reference

## Quick start (local)

Run Calibre-Web with the dev compose overlay (exposes `http://localhost:8083`):

```bash
docker compose -f compose.yml -f compose.dev.yml up -d --build
```

Optional: run the smoke script (starts containers if needed and performs basic checks):

```bash
bash .github/qa/scripts/smoke.sh
```

## Roles to test

Use these three personas consistently (agents should follow `e2e/roles_smoke.md`):

### 1) Anonymous (not logged in)
- Can load `/` (status 200)
- Does **not** see admin nav injection items (`#top_users_books`, `#top_orders`)
- Visiting `/admin/ebookslv/` redirects to login

### 2) Non-admin user (logged in)
- Can browse catalog
- Does **not** see admin nav injection items
- Visiting `/admin/ebookslv/` redirects/denies (not an admin)
- When a Mozello order record exists for their email, their purchased book(s) become available under the injected catalog scope (see `e2e/non_admin_catalog_scope.md`)

### 3) Admin user (logged in)
- Sees injected admin nav links:
	- `#top_users_books` -> `/admin/ebookslv/` (ebooks.lv hub)
	- `#top_orders` -> `/admin/ebookslv/orders/`
- Can open `/admin/ebookslv/` and `/admin/ebookslv/orders/`
- Mozello admin is reachable from the Mozello card on `/admin/ebookslv/`

## Bootstrap scripts (inside container)

These scripts are designed to be run via `docker compose exec` against the running container:

```bash
# Ensure admin exists and password is set
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web \
	python /app/.github/qa/scripts/bootstrap_admin.py

# Ensure a deterministic non-admin user exists
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web \
	python /app/.github/qa/scripts/bootstrap_non_admin_user.py

# Create/update a deterministic Mozello order record for the non-admin user
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web \
	python /app/.github/qa/scripts/bootstrap_order_for_non_admin.py
```

## Notes
- This repo’s current access gating is based on **Mozello orders** (users_books DB) and catalog overrides, not the legacy allow-list UI.
- Keep scripts **idempotent** and **container-friendly** (no host-specific paths).
