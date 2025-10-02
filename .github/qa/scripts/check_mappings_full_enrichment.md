# Script: Verify /admin/users_books/mappings_full enrichment

Objective: Ensure each mapping JSON object now contains `email` and `title` keys (non-empty when source data exists) and UI table renders those values.

Manual Steps (to be automated via Chrome DevTools MCP):
1. Login as admin (username `admin`, password from credentials.env `admin123`).
2. Navigate to `/admin/users_books`.
3. Open network panel, trigger refresh by clicking `#ub-reload-mappings`.
4. Inspect XHR `GET /admin/users_books/mappings_full` response JSON:
   - Assert every element has keys: `user_id`, `book_id`, `email`, `title`.
5. In DOM, locate first data row (skip empty-state). Confirm first row's first TD text equals `email` field and third TD equals `title`.
6. If table empty (no mappings), optionally add one mapping then re-run steps 3–5.

Pass Criteria:
- JSON includes `email` and `title` fields (even if blank when unknown) for all mappings.
- Table columns "User Email" and "Book Title" populated (non-empty) for at least one mapping after creating one if necessary.

Automation Notes:
- Use `document.querySelectorAll('#ub-mappings-tbody tr')` to get rows.
- Skip rows where single TD has `No mappings present.`
- Use fetch in page context: `await (await fetch('/admin/users_books/mappings_full')).json()`.
