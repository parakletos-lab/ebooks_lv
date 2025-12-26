# E2E: Admin Operator Manual (ebooks.lv Hub)

Purpose: Verify the Operator manual card exists on the ebooks.lv hub page and the manual content switches based on the selected UI language.

## Preconditions
- Local dev container running: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Admin user exists (recommended):
  - `docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_admin.py`

## Steps
1. Open `http://localhost:8083/`.
2. Log in as admin.
3. Open `http://localhost:8083/admin/ebookslv/`.
4. Confirm a card titled "Operator manual" is visible.
5. Click "Open" on that card.
6. Expect `/admin/ebookslv/operator-manual/` to load (status 200).
7. Confirm the page renders formatted HTML content (headings/lists), not raw preformatted text.
8. Click the top-nav language switch buttons and verify the page title updates:
   - Click "ENG" → title becomes "Operator manual"
   - Click "RUS" → title becomes "Инструкция пользователя"
   - Click "LAT" → title becomes "Lietošanas instrukcija"

## Pass Criteria
- Operator manual card is present on `/admin/ebookslv/`.
- Clicking it loads `/admin/ebookslv/operator-manual/`.
- Language switching changes the title and shows the corresponding localized manual content.
