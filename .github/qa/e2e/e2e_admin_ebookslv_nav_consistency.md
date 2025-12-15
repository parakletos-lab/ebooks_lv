# E2E: ebooks.lv admin page uses standard Calibre-Web chrome

Goal: Ensure `/admin/ebookslv/` renders with the same navbar title and sidebar menu as the home page.

## Preconditions

- Start QA stack: `bash .github/qa/scripts/run_all.sh`
- Login credentials (defaults):
  - Admin: `admin@example.org` / `AdminTest123!`

## Steps

1. Open home page: `http://localhost:8083/`
2. Confirm left sidebar is present (e.g. entries like **Books**, **Free**).
3. Click the top-left brand/title area.
   - Confirm it shows the Calibre-Web instance title (not blank).
4. Open ebooks.lv admin landing: `http://localhost:8083/admin/ebookslv/`
5. Confirm the page keeps the same Calibre-Web chrome:
   - Top-left brand/title is present (not blank)
   - Left sidebar menu is present and looks like the home page

## Expected

- `/admin/ebookslv/` matches the same header + sidebar layout as `/`.
- No missing/blank title in the top-left corner.
