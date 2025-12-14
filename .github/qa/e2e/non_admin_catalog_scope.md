# E2E: Non-admin Catalog Scope (Purchased / All / Free)

Goal: Validate the non-admin catalog override behavior driven by Mozello orders.

## Preconditions
- Container running: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Deterministic non-admin user exists.
- Seed a Mozello order record for that user (marks one Calibre book as purchased):

```bash
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web \
  python /app/.github/qa/scripts/bootstrap_order_for_non_admin.py
```

## Steps
1. Login as non-admin user (`QA_USER_USERNAME` / `QA_USER_PASSWORD`).
2. Open `/`.
3. In page source or DOM:
   - Assert catalog payload script exists: `#mozello-catalog-state`.
4. Click "Free Books" (or open `/catalog/free-books`).
   - Expect no login redirect (anon allowed) and nav item `#nav_freebooks` active.
   - Open a free book detail modal (price 0 or missing) and assert the "Read in Browser" button is present and no "Buy Online" button.
5. Click "My Books" (or open `/catalog/my-books`).
   - Expect redirect to login when anonymous; when logged in, shows purchased-only scope.
6. Click "All Books" (or open `/catalog/all-books`).

## Pass Criteria
- Non-admin sees the catalog scope UI injected (payload script and JS/CSS markers).
- `/catalog/free-books` reachable anonymously; free detail modal shows "Read in Browser" and no "Buy Online".
- `/catalog/my-books` redirects to login when anonymous, but works when logged in.
