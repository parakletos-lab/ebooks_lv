# E2E: Role Smoke (Anonymous / Non-admin / Admin)

Target: local dev container at `http://localhost:8083`.

## 0) Preconditions
- Run: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- (Recommended) Run bootstrap:
  - `docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_admin.py`
  - `docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_non_admin_user.py`

## 1) Anonymous (not logged in)
1. Open `/`.
2. Assert admin nav items are not present:
   - `#top_users_books`, `#top_orders`, `#top_mozello`.
3. Try to open `/admin/ebookslv/`.
4. Expect redirect to login (or login page).

## 2) Non-admin user
1. Login as `QA_USER_USERNAME` / `QA_USER_PASSWORD` from `.github/qa/credentials.env`.
2. Assert admin nav items are not present:
   - `#top_users_books`, `#top_orders`, `#top_mozello`.
3. Try to open `/admin/ebookslv/`.
4. Expect redirect/deny (non-admin).

## 3) Admin user
1. Login as `QA_ADMIN_USERNAME` / `QA_ADMIN_PASSWORD`.
2. Assert injected nav items are present:
   - `#top_users_books` -> `/admin/ebookslv/`
   - `#top_orders` -> `/admin/ebookslv/orders/`
   - `#top_mozello` -> `/admin/mozello/`
3. Open `/admin/ebookslv/` and `/admin/ebookslv/orders/`.
4. Expect both pages to render (status 200).
