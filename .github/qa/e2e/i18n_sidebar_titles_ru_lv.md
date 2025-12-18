# E2E: i18n sidebar labels + ebookslv titles

Goal: Ensure sidebar link labels are localized correctly and ebooks.lv is not present in ebookslv page titles for LV/RU/EN.

## Preconditions

- Start QA stack: `bash .github/qa/scripts/run_all.sh`
- Login credentials (defaults):
  - Admin: `admin@example.org` / `AdminTest123!`

## Steps

### Latvian: About link text

1. Open `http://localhost:8083/`
2. Switch language to **LAT**.
3. In the left sidebar, confirm the **About** link label is **Par sistēmu**.

### Russian: missing sidebar labels

1. Switch language to **RUS**.
2. In the left sidebar, confirm these items are in Russian (not English):
   - **Скачанные книги** (Downloaded Books)
   - **Архивированные книги** (Archived Books)
   - **Список книг** (Books List)

### ebookslv titles (LV/RU/EN)

1. Navigate to `http://localhost:8083/admin/ebookslv/`.
2. Confirm the browser/tab title does **not** contain `ebooks.lv` for:
   - **ENG** (should be `Calibre-Web | Admin`)
   - **RUS** (should be `Calibre-Web | Администрация`)
   - **LAT** (should be `Calibre-Web | Administrācija`)
3. Navigate to `http://localhost:8083/admin/ebookslv/books/`.
4. Confirm the page heading does **not** contain `ebooks.lv`:
   - **ENG** heading `Books Sync`
   - **RUS** heading `Синхронизация книг`
   - **LAT** heading `Grāmatu sinhronizācija`

## Expected

- LV sidebar shows **Par sistēmu**.
- RU sidebar shows translated labels for Downloaded/Archived/Books List.
- ebookslv admin + books pages have titles/headings without `ebooks.lv`.
