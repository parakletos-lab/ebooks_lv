# Reader: Disable text copy (non-admin + anonymous)

Goal: verify the in-browser reader pages block common copy paths for non-admin users and anonymous readers.

## Setup

- Run: `bash .github/qa/scripts/run_all.sh`
- Open: `http://localhost:8083/`

Credentials (defaults used by QA scripts):
- Non-admin: `qa_user@example.test` / `qa_user123`
- Admin: `admin@example.org` / `AdminTest123!`

## Non-admin (should be blocked)

1) Login as non-admin.
2) Open book details for a book that has an in-browser reader button (example in seeded library: book id `3`, “Labyrintti”).
3) Click “Lasīt pārlūkā - epub” (or any reader format button).
4) Verify copy is blocked:
   - Right click should not open context menu.
   - Attempt to select text in the reader content should not produce a selection.
   - Keyboard copy shortcut should be blocked:
     - macOS: `⌘+C`
     - Windows/Linux: `Ctrl+C`

## PDF (should be blocked)

If a PDF format is available for any book:
1) Open “Lasīt pārlūkā - pdf”.
2) Verify PDF.js text selection does not work (text layer should not be selectable).
3) Verify right click and copy shortcuts are blocked as above.

## Admin (should NOT be blocked)

1) Login as admin.
2) Open the same reader page.
3) Verify the anti-copy assets are NOT injected (admin should behave like upstream).
