# E2E: Admin Mozello Card (ebooks.lv Hub)

Purpose: Verify that Mozello admin access is available via the ebooks.lv hub page (and not via the top navigation).

## Preconditions
- Local dev container running: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Admin user exists (recommended):
  - `docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_admin.py`

## Steps
1. Open `http://localhost:8083/`.
2. Log in as admin.
3. In the top navigation, confirm **no** "Mozello" link is present.
4. Open `http://localhost:8083/admin/ebookslv/`.
5. Confirm a card titled "Mozello" is visible.
6. Click "Open" on that card.
 7. Expect `/admin/ebookslv/mozello/` to load (status 200).
 8. Open `http://localhost:8083/admin/mozello/`.
 9. Expect it to redirect to `/admin/ebookslv/mozello/`.

## Pass Criteria
- Mozello is not present as a top-nav injected link.
- Mozello is present as a card on `/admin/ebookslv/`.
 - The Mozello card opens `/admin/ebookslv/mozello/`.
 - Legacy `/admin/mozello/` redirects to `/admin/ebookslv/mozello/`.
````markdown
# E2E: Admin Mozello Card (ebooks.lv Hub)

Purpose: Verify that Mozello admin access is available via the ebooks.lv hub page (and not via the top navigation).

## Preconditions
- Local dev container running: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Admin user exists (recommended):
  - `docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_admin.py`

## Steps
1. Open `http://localhost:8083/`.
2. Log in as admin.
3. In the top navigation, confirm **no** "Mozello" link is present.
4. Open `http://localhost:8083/admin/ebookslv/`.
5. Confirm a card titled "Mozello" is visible.
6. Click "Open" on that card.
7. Expect `/admin/mozello/` to load (status 200).

## Pass Criteria
- Mozello is not present as a top-nav injected link.
- Mozello is present as a card on `/admin/ebookslv/`.
- The Mozello card opens `/admin/mozello/`.

````
