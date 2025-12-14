# E2E: Admin Nav Link Visibility

Purpose: Verify that the integrated app layer injects ebooks.lv admin navigation links for admin users and hides them for non-admins.

## Preconditions
- Container running locally (see Build & Run below)
- Admin credentials: admin / admin123 (adjust if changed)
- Non-admin user exists (or create one through Calibre-Web UI)

## Steps (Admin Should See Link)
1. Open http://localhost:8083
2. Log in as admin.
3. Wait for page load; ensure element with id `top_admin` exists.
4. Assert these links are present in the DOM:
	- `#top_users_books` (ebooks.lv hub)
	- `#top_orders`
5. Click each link and confirm it loads:
	- `#top_users_books` -> `/admin/ebookslv/`
	- `#top_orders` -> `/admin/ebookslv/orders/`

## Steps (Non-Admin Should NOT See Link)
1. Log out.
2. Log in as a non-admin user.
3. Confirm `top_admin` absent (or present only if that user has admin rights by mistake).
4. Confirm `top_users_books`, `top_orders` are absent.

## Note
- Mozello admin is reachable from the Mozello card on `/admin/ebookslv/`.

## Network Assertions (Optional via DevTools MCP)
- Capture network; expect no failing XHR/Fetch on initial catalog load.

## Pass Criteria
- Admin sees `#top_users_books`, `#top_orders`.
- Non-admin sees none of these admin nav items.
- No console errors related to nav injection.

## Build & Run
```
docker compose build --no-cache
docker compose up -d
```

## Teardown
```
docker compose down
```
