# E2E: ebooks.lv Books table — no “Mozello Title” column

Purpose: Verify that the `/admin/ebookslv/books/` table no longer shows the “Mozello Title” column.

## Preconditions
- Local dev container running: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Admin user exists (recommended):
  - `docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_admin.py`

## Steps
1. Open `http://localhost:8083/`.
2. Log in as admin.
3. Open `http://localhost:8083/admin/ebookslv/books/`.
4. In the table header row, verify the columns include:
   - “Book ID”, “Title”, “Price”, “Sync / State”, “Delete”.
5. Verify the header does NOT include “Mozello Title”.
6. Click “Reload Calibre Books” and confirm the table renders rows (if your library has books).

## Pass Criteria
- “Mozello Title” is not present as a table column on `/admin/ebookslv/books/`.
- Other columns and actions still render and work.
