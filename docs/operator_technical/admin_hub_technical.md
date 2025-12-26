# ebooks.lv Admin Hub (Technical)

This is the technical reference for the `/admin/ebookslv/` landing page and the pages behind its cards.

Scope:
- URLs
- templates
- route owners
- how the hub action button works

This document does not repeat the full operational procedures; it links to the dedicated operator/technical docs.

---

## 1) Hub page

- URL: `/admin/ebookslv/`
- Route: `landing()` in [app/routes/admin_ebookslv.py](app/routes/admin_ebookslv.py)
- Template: [app/templates/ebookslv_admin.html](app/templates/ebookslv_admin.html)

Admin enforcement:
- Uses `ensure_admin()` (redirects to `/login?next=...` when not admin).

---

## 2) Cards → pages mapping

### 2.1 Orders card
- URL: `/admin/ebookslv/orders/`
- Route: `orders_page()` in [app/routes/admin_ebookslv.py](app/routes/admin_ebookslv.py)
- Template: [app/templates/orders_admin.html](app/templates/orders_admin.html)

What it does:
- Admin UI for importing Mozello paid orders and managing “who can read what” by creating/updating orders and linking them to Calibre-Web users.

Related docs (deeper):
- docs/operator/user_management.md
- docs/operator/user_management_technical.md

### 2.2 Mozello card
- URL: `/admin/ebookslv/mozello/` (legacy `/admin/mozello/` redirects here)
- Route owner: [app/routes/admin_mozello.py](app/routes/admin_mozello.py)

What it does:
- Admin UI for Mozello integration settings and operational tooling (webhook/config related), plus supporting routes like `/mozello/books/<handle>`.

Related docs (deeper):
- docs/mozello_purchase_login_flow.md
- .github/instructions/mozello_store_api.md

### 2.3 Books card
- URL: `/admin/ebookslv/books/`
- Route: `books_page()` in [app/routes/admin_ebookslv.py](app/routes/admin_ebookslv.py)
- Template: [app/templates/ebookslv_books_admin.html](app/templates/ebookslv_books_admin.html)

What it does:
- Admin UI for syncing Calibre library metadata to Mozello products, including export/upsert, price syncing, and product maintenance actions.

Related docs (deeper):
- docs/operator/books_management.md
- docs/operator/books_management_technical.md

### 2.4 Email Templates card
- URL: `/admin/ebookslv/email-templates/`
- Route: `email_templates_page()` in [app/routes/admin_ebookslv.py](app/routes/admin_ebookslv.py)
- Template: [app/templates/email_templates_admin.html](app/templates/email_templates_admin.html)

What it does:
- Admin UI for managing email template records stored in the users_books DB (token allow-lists and persistence rules are managed via the service layer).

Related docs (deeper):
- .github/instructions/email_templates.md

---

## 3) Hub button: “Set default settings”

UI behavior:
- The button is in [app/templates/ebookslv_admin.html](app/templates/ebookslv_admin.html).
- It POSTs to `/admin/ebookslv/apply_defaults` with `X-CSRFToken` header.

Backend behavior:
- Route: `api_apply_defaults()` in [app/routes/admin_ebookslv.py](app/routes/admin_ebookslv.py)
- Applies curated defaults to upstream Calibre-Web config:
  - default role mask (viewer + password)
  - sidebar visibility mask
  - uploading enabled
  - title set from `APP_TITLE` via `app.config.app_title()` (if configured)

Operational notes:
- This is a settings convenience action; it does not touch Mozello or library contents.
- If Calibre runtime is unavailable, the route returns a 503 error (`calibre_runtime_unavailable`).
