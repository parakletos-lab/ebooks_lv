# Updating the upstream Calibre-Web submodule

This repo vendors upstream Calibre-Web as a **git submodule** at `./calibre-web/`.

Goal: update the pinned Calibre-Web commit (preferably to a tag/release) while keeping our wrapper/overrides working.

## Constraints / guardrails

- Do **not** edit files under `calibre-web/` directly unless you have explicit approval to do so.
- Prefer upgrading to an upstream **tag** (release). Only pin to an unreleased commit when you are intentionally taking a fix from `origin/master`.
- After an upgrade, always rebuild the docker image and run the repo QA/e2e checks.

## 1) Identify the current pinned version

From repo root:

```bash
git submodule status
# and inside the submodule:
git -C calibre-web describe --tags --always --dirty
```

Useful additional context:

```bash
git -C calibre-web remote -v
# list newest tags
git -C calibre-web tag --sort=-version:refname | head
```

## 2) Decide the target

Recommended order:

1. Latest stable tag (e.g. `0.6.xx`).
2. A newer tag that includes the specific fix/feature you want.
3. A specific upstream commit on `origin/master` (unreleased) **only if necessary**.

When pinning to an unreleased commit, record:

- the exact commit SHA
- why you need it (issue/PR link)
- the risk (future tags may diverge)

## 3) Inspect upstream changes before you bump

High-signal commands (run inside `calibre-web/`):

```bash
# commits since the current tag (example)
git log --oneline <old_tag_or_sha>..<new_tag_or_sha> | head -n 80

# where changes concentrate
git diff --dirstat=files,0 <old>..<new>

# what files are deleted/renamed (break risk)
git diff --name-status <old>..<new> | head -n 200
```

Focus review on:

- `cps/db.py` (ORM/model/query changes)
- `cps/render_template.py` + `cps/templates/` (template context, layout changes)
- `cps/static/` (JS/CSS changes affecting our injected styles)
- `requirements.txt` / optional requirements (dependency changes)
- auth/session/login flows (`cps/cw_login.py`, `cps/usermanagement.py`)

## 4) Upgrade the submodule pointer

From repo root:

```bash
# update refs
git -C calibre-web fetch --tags origin

# choose one:
# A) pin to a tag
git -C calibre-web checkout <tag>

# B) pin to an unreleased commit
git -C calibre-web checkout <sha>

# record the new pointer in the parent repo
git add calibre-web
```

If the submodule has local changes (it should not), stop and reset:

```bash
git -C calibre-web status
# if needed:
git -C calibre-web reset --hard
```

## 5) Rebuild and run verification

Rebuild container after any change affecting upstream UI/backend:

```bash
docker compose up -d --build calibre-web-server
```

Then run the repo QA/e2e suite:

```bash
bash .github/qa/scripts/run_all.sh
```

Manual smoke checks (browser):

- Login/logout flow (including password reset)
- Catalog browse + book details
- Read flow (especially free/anonymous behavior if enabled)
- Admin pages added by this repo (ebooks.lv admin + Mozello admin)
- Verify HTML responses still include the hidden CSRF `<input>` on admin pages before testing POST actions

## 6) Things most likely to break in *this* repo

This wrapper integrates with Calibre-Web via runtime overrides and direct imports from the `cps` package. The highest-risk areas to re-check after an upgrade:

- `app/routes/login_override.py` (relies on `cps.render_template.render_title_template`, `cps.config`, `cps.cw_login` helpers)
- `app/routes/admin_ebookslv.py` and `app/routes/admin_mozello.py` (relies on `cps.csrf`, Calibre-Web template context conventions)
- `app/routes/overrides/*` (monkey-patches endpoints and injects HTML/CSS)
- `app/services/email_delivery.py` (relies on `cps.tasks.mail.TaskEmail` and `cps.services.worker.WorkerThread`)
- Any CSS/JS selectors tied to upstream templates (e.g. Mozello theme injection)

If something breaks, prefer adapting our wrapper code (service/override layer) instead of patching upstream.

## 7) Rollback plan

Rolling back is just reverting the submodule pointer:

```bash
# from parent repo, checkout a known-good commit
# or revert the submodule bump commit

git checkout <known_good_parent_commit>
# then ensure submodule state matches

git submodule update --init --recursive
```

Rebuild docker image again after rollback.
