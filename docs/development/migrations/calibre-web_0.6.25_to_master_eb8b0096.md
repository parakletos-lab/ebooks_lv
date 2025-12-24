# Calibre-Web migration: 0.6.25 → origin/master (eb8b0096)

This document is a **deep dive** for upgrading the vendored Calibre-Web submodule from tag `0.6.25` to upstream `origin/master` at commit `eb8b0096`.

Context (current workspace state when written): this repo is already pinned slightly past the `0.6.25` tag (`0.6.25-2-g0ff1feae`). That means you may already have two post-tag fixes locally, and the “real” delta to `origin/master` is still large.

> Note: `origin/master` here is **unreleased** (no newer tag in the submodule at time of writing). Upgrading to master can yield important fixes/features but is higher-risk than upgrading to a tag.

## What changed upstream (high-level)

Between `0.6.25` and `origin/master@eb8b0096`, upstream changes concentrate in:

- Core Python package `cps/` (routes, helpers, db layer)
- Templates under `cps/templates/` (layout/read/list/config screens)
- Static assets under `cps/static/` (reader JS/CSS, theme/UX improvements)
- Many translation updates

Notable theme buckets visible in upstream history:

- Reader UX improvements (epub.js behavior, viewport sizing, theme selection)
- UI tweaks for mobile/small screens
- Search performance optimizations (query changes)
- Some auth-related behavior adjustments (e.g., 401 responses include `WWW-Authenticate`)
- Dependency/requirements updates

## Integration risk map for ebooks.lv wrapper

This repo integrates with Calibre-Web via **runtime imports** from `cps.*` and runtime endpoint/template injections. That means most breaking risks show up as:

- Import paths/symbols renamed
- Function signatures changed
- Endpoint names changing (Flask endpoint keys)
- Template structure changes (our HTML injection hooks fail)
- CSS selectors no longer matching

### Direct imports to re-validate

These are the key symbols imported by our wrapper that you should verify after bumping:

- `cps.render_template.render_title_template`
- `cps.csrf`
- `cps.ub` (user DB / babel integration)
- `cps.cw_login` (`login_user`, `logout_user`, `current_user`)
- `cps.redirect.get_redirect_location`
- `cps.tasks.mail.TaskEmail`
- `cps.services.worker.WorkerThread`
- `cps.constants`, `cps.db` (used indirectly by monkey patches)

At commit `eb8b0096`, the symbols above still exist by name, but you must re-run a real application boot + smoke tests because behavior can still change.

## Likely breaking points & fixes

### 1) Database layer changes (`cps/db.py`)

Upstream made substantial changes in `cps/db.py` in the master delta.

Why it matters:

- Our monkeypatch in `app/routes/overrides/calibre_overrides.py` patches `CalibreDB.common_filters` and relies on `Books.id` existing and being compatible with SQLAlchemy `in_()` filtering.

What to check:

- `CalibreDB` class still exists
- `CalibreDB.common_filters(allow_show_archived=False, return_all_languages=False)` signature unchanged
- `Books` model still exists and `Books.id` is the expected primary key column

If it breaks:

- If `Books` is renamed/moved: update the monkeypatch to target the new model symbol.
- If `common_filters` signature changes: update wrapper signature to accept `*args, **kwargs` and pass through.
- If common filter logic changes: verify the returned clause type is compatible with `and_()`.

### 2) Endpoint replacement by name (Flask endpoint keys)

We patch endpoints by name (e.g. `web.read_book`, `web.serve_book`). If upstream renames endpoints or changes decorators, our `__wrapped__` unwrapping can fail.

What to check:

- Endpoint keys still exist in `app.view_functions`.
- Views still expose `__wrapped__` twice (decorator stacking pattern).

If it breaks:

- If endpoint name changes, search upstream for the new endpoint name and update our patch key.
- If decorator wrapping changes, avoid deep unwrapping and instead wrap the existing function directly (best-effort). Keep the “fail closed” behavior for protected content.

### 3) Template/HTML injection fragility

We inject extra content (navigation, theme CSS, language switch, etc.) by editing HTML responses. Upstream template changes can:

- move/duplicate `<head>` / `<body>` boundaries
- change layout containers
- change IDs/classes used by our CSS

What to check:

- The injected `<link>` tag for the Mozello stylesheet appears exactly once.
- The nav injection still renders in the right place.

If it breaks:

- Update injection strategy to target a more stable anchor (e.g. inject before `</head>` rather than after a specific tag).
- Keep injections idempotent by using an explicit marker attribute (already done for the Mozello theme).

### 4) Static assets and reader behavior changes

Master includes meaningful changes to reader JS/CSS. Even if our Python overrides still work, the UX can change.

What to check:

- Reading an EPUB renders, pages turn, and stored reading position behaves as expected.
- No JS errors in browser console.
- Our CSS overrides (Mozello theme) still match upstream classnames.

If it breaks:

- Prefer adjusting our CSS selectors to match the new upstream markup.
- If upstream introduces new CSP or changes existing CSP behavior, ensure our injection is still compatible.

### 5) Environment variable rename risk (upstream)

Upstream history includes an env var rename (`CACHE_DIR` → `CACHE_DIRECTORY`) in the master delta.

In this repo, `CACHE_DIR` is not referenced in docker compose overlays at time of writing; however, operators might set it externally.

If you rely on cache env vars:

- Update deployment configuration to use the new upstream name.
- Consider setting both names temporarily during migration (if upstream supports fallback) to avoid a hard cut-over.

## Verification checklist (do this after bumping)

1. Rebuild container:

```bash
docker compose up -d --build calibre-web-server
```

2. Run QA:

```bash
bash .github/qa/scripts/run_all.sh
```

3. Manual smoke (browser):

- Login/logout
- Password reset (email workflow + token acceptance)
- Catalog browse
- Book details page
- Reader open (free + purchased flows)
- Admin ebooks.lv pages
- Admin Mozello pages

4. Specific wrapper checks:

- Free-book anonymous read path works (ensures our `web.read_book` and `web.serve_book` patches still apply).
- CSS injection marker present (`data-eblv-mozello-theme`).

## Recommended migration approach

Because this is a large jump to unreleased `master`, treat it as a controlled rollout:

- Create a single “submodule bump” PR/commit (only the submodule pointer changes).
- Run the full QA suite and manual smoke checks.
- If any wrapper fixes are required, add them as follow-up commits in the same PR.
- If fixes become extensive, reconsider waiting for an upstream tag/release.

## Rollback

Rollback is reverting the parent repo commit that changes the submodule pointer, then syncing submodules:

```bash
git submodule update --init --recursive
```

Rebuild docker image again after rollback.
