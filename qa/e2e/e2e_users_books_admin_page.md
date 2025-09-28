```markdown
# E2E: Users ↔ Books Admin Page

Purpose: Validate the integrated admin UI at `/admin/users_books` loads, lists non-admin users, lists books, and exposes mapping endpoints.

## Preconditions
- Container running (`docker compose up -d`)
- Admin credentials: `admin / admin123`
- At least one non-admin real user exists (e.g. `deniss`, `qa_filter`). If needed run `python .github/qa/scripts/create_non_admin_user.py` (legacy helper) or create via Calibre-Web UI.

## Steps
1. Open http://localhost:8083/admin/users_books (will redirect to login if not authenticated).
2. Log in as admin; page should render with heading `users_books Allow‑List Management`.
3. Assert Users panel:
   - Contains at least 1 checkbox with email matching a known non-admin (e.g. `deniss.muhla@gmail.com`).
   - No admin or anonymous users listed (emails for admin@example.org or Guest should not appear).
4. Assert Books panel:
   - Contains at least 1 checkbox with known book id (#2 or #3 based on seed data).
5. Press `Refresh Mapping List` – mappings table should show zero or more rows (status panel logs `Mappings loaded:` line).
6. (Optional) Select one user + one book, click `Add Selected Mappings`, observe log success line and table growth or `exists` status.
7. Click delete (trash icon) for a mapping row – row should disappear and log `deleted`.

## API Spot Checks (curl or browser)
- GET /admin/users_books/all_users returns JSON with `users` array length >= 1.
- GET /admin/users_books/all_books?limit=2 returns <= 2 books.
- GET /admin/users_books/mappings_full returns JSON with `mappings` field.

## Pass Criteria
- Page accessible at `/admin/users_books`.
- Non-admin users listed, admin/anonymous excluded.
- Books listed.
- Creating and deleting a mapping updates table and log without errors.
- Network calls return HTTP 200 (except expected 302 redirect from `/users_books/admin` legacy path).

## Failure Signals
- Users panel empty (investigate `_fetch_non_admin_users`).
- HTTP 403 on any `/admin/users_books/*` despite admin login.
- Console errors referencing `users_books` or failed fetches.

## Notes
- Legacy paths `/admin/users_books/admin` (UI) still work.
- Old path `/users_books/admin` redirects 302 to canonical path.

```