# Books Management (Technical)

This document is the technical reference for how ebooks.lv manages books across:

- Calibre library (authoritative storage for book files + metadata)
- ebooks.lv reader app (Calibre-Web + overrides)
- Mozello shop (storefront + payments)

This is intended for developers / technical operators.

---

## 1) Data model (the 3 linking fields)

### 1.1 `mz_price` (Calibre custom column)
- Stored in Calibre library `metadata.db` as a custom float column labeled `mz_price`.
- Created/ensured at startup via [entrypoint/seed_library.py](entrypoint/seed_library.py) (idempotent).
- Used by the reader app to determine FREE vs paid:
  - missing or 0 → treated as FREE
  - > 0 → treated as paid/available

Code paths:
- `app/services/books_sync.py` reads/writes via Calibre sqlite.
- `app/services/catalog_access.py` treats missing/0 as free via `books_sync.list_free_book_ids()`.

### 1.2 `mz_handle` (Calibre identifier type `mz`)
- Stored in Calibre identifiers table with `type='mz'`.
- Represents Mozello product handle; is the join key for:
  - admin book sync UI
  - Mozello order → purchased book mapping
  - storefront redirect `/mozello/books/<handle>`

Default handle convention used by export:
- `book-<calibre_book_id>`

### 1.3 `mz_relative_url` (Calibre identifier type `mz_relative_url`)
- Cached Mozello “relative URL” for product.
- Used as fallback for redirects if Mozello API URL resolution fails.

Related identifiers:
- `mz_cover_uids` (JSON list) stores uploaded cover picture UID(s).
- `mz_pictures` (JSON list) stores Mozello pictures list (uid+url).

---

## 2) Operator UI pages and routes

### 2.1 Admin hub
- UI page: `/admin/ebookslv/` (links to Books/Orders/Mozello settings)

### 2.2 Books sync UI
- UI page: `/admin/ebookslv/books/`
- Template: [app/templates/ebookslv_books_admin.html](app/templates/ebookslv_books_admin.html)

Books JSON endpoints (admin-only; some are CSRF-exempt due to Calibre-Web csrf wrapper):
- `GET /admin/ebookslv/books/api/data` → list Calibre books
- `POST /admin/ebookslv/books/api/load_products` → fetch Mozello products and merge into the table; persists `mz_relative_url`
- `POST /admin/ebookslv/books/api/sync_prices_from_mozello` → updates Calibre `mz_price` from Mozello
- `POST /admin/ebookslv/books/api/push_prices_to_mozello` → updates Mozello price from Calibre
- `POST /admin/ebookslv/books/api/export_one/<book_id>` → upsert product + best-effort cover upload; persists handle & relative url
- `POST /admin/ebookslv/books/api/export_all` → export only books with positive `mz_price` and missing `mz_handle`
- `DELETE /admin/ebookslv/books/api/delete/<handle>` → deletes Mozello product and clears local identifiers (`mz_handle`, `mz_relative_url`, `mz_cover_uids`)

Implementation: [app/routes/admin_ebookslv.py](app/routes/admin_ebookslv.py)

### 2.3 “Sync to Mozello” button on book pages
- Injected into `/book/<id>` pages for admin users.
- Clicking it calls `POST /admin/ebookslv/books/api/export_one/<book_id>`.

Implementation: [app/routes/overrides/mozello_sync_injection.py](app/routes/overrides/mozello_sync_injection.py)

### 2.4 Storefront product redirect
- `GET /mozello/books/<handle>?lang=lv|ru|en`
- Resolves storefront URL via Mozello API; falls back to cached `mz_relative_url`.

Implementation: [app/routes/admin_mozello.py](app/routes/admin_mozello.py)

---

## 3) Sync behavior details

### 3.1 Export one (`export_one`)
- Chooses handle:
  - existing `mz_handle` OR `book-<book_id>`
- Upserts product basics (title, price, description, language_code) via `mozello_service.upsert_product_basic`.
- If handle was newly created, persists `mz_handle` to Calibre.
- Attempts to derive & persist `mz_relative_url`:
  - from upsert response; else fetches product and derives.
- Best-effort cover upload:
  - reads Calibre `cover.jpg` base64 via `books_sync.get_cover_base64`.
  - calls `mozello_service.ensure_cover_picture_present`.
  - stores uploaded UID in `mz_cover_uids`.

### 3.2 Export all (`export_all`)
- Exports only rows where:
  - `mz_handle` missing AND
  - `mz_price` is numeric and > 0
- Uses `handle = book-<book_id>` convention.
- Also best-effort cover upload.

### 3.3 Load products
- Calls `mozello_service.list_products_full()`.
- For every product, persists/clears `mz_relative_url` locally.
- Merges remote product title/price into local rows and creates “orphan” rows.

### 3.4 Price sync semantics
- “Sync Prices from Mozello” updates local Calibre prices for matching handles.
- “Push Prices to Mozello” updates remote Mozello prices for rows with both handle and non-null price.

---

## 4) Purchase → reader access mapping

High-level flow:
1. Mozello purchase triggers webhook to `/mozello/webhook`.
2. Orders service stores purchased Mozello handle(s).
3. Reader access is computed per request:
   - purchased book IDs from orders
   - plus free book IDs from `mz_price` logic

Related docs:
- [docs/mozello_purchase_login_flow.md](docs/mozello_purchase_login_flow.md)

---

## 5) Troubleshooting (technical)

### 5.1 “Export failed”
- Likely Mozello API failure (auth, validation, HTTP error).
- Confirm API key and Mozello app settings in `/admin/ebookslv/mozello/`.
- Use single export (`export_one`) to isolate a problematic record.

### 5.2 Redirect `/mozello/books/<handle>` returns 404/503
- 404: no handle or no cached relative url and API resolution failed.
- 503: cached relative url exists but URL resolution still failed.

Actions:
- Refresh cached relative URLs via `POST /admin/ebookslv/books/api/load_products`.
- Re-export a book to force-refresh relative URL.

### 5.3 Cover upload issues
- Cover upload reads `<library_root>/<book.path>/cover.jpg`.
- Large covers may be skipped (size cap in `books_sync.get_cover_base64`).

---

## 6) Mozello API reference

Engineering notes live here:
- [ .github/instructions/mozello_store_api.md ](.github/instructions/mozello_store_api.md)

(Keep that file as the single authoritative internal summary; don’t duplicate large excerpts elsewhere.)
