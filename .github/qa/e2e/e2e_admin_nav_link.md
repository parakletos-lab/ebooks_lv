# E2E: Admin Nav Link Visibility

Purpose: Verify that the integrated app layer injects the ebooks.lv navigation link for admin users and hides it for non-admins.

## Preconditions
- Container running locally (see Build & Run below)
- Admin credentials: admin / admin123 (adjust if changed)
- Non-admin user exists (or create one through Calibre-Web UI)

## Steps (Admin Should See Link)
1. Open http://localhost:8083
2. Log in as admin.
3. Wait for page load; ensure element with id `top_admin` exists.
4. Assert element with id `top_users_books` is present in the DOM.
5. Click the link; expect admin UI endpoint `/plugin/users_books/admin/ui` (or JSON endpoints if UI not yet migrated) to respond 200.

## Steps (Non-Admin Should NOT See Link)
1. Log out.
2. Log in as a non-admin user.
3. Confirm `top_admin` absent (or present only if that user has admin rights by mistake).
4. Confirm `top_users_books` is absent.

## Network Assertions (Optional via DevTools MCP)
- Capture network; expect no failing XHR/Fetch related to `/plugin/users_books` on initial catalog load.

## Pass Criteria
- Admin sees `#top_users_books`.
- Non-admin does not see `#top_users_books`.
- No console errors containing `users_books nav`.

## Build & Run
```
docker compose build --no-cache
docker compose up -d
```

## Teardown
```
docker compose down
```
