# User Management (Technical)

This document describes the technical mechanisms behind user + access management in ebooks.lv.

Scope:
- creating/linking Calibre-Web users
- granting/revoking access via Mozello order records
- password reset / initial login token mechanics

---

## 1) Primary admin UI and API

### 1.1 Orders admin UI
- UI page: `/admin/ebookslv/orders/`
- Template: [app/templates/orders_admin.html](app/templates/orders_admin.html)

The UI calls these JSON endpoints:
- `GET /admin/ebookslv/orders/api/list`
- `POST /admin/ebookslv/orders/api/create`
- `POST /admin/ebookslv/orders/api/<order_id>/create_user`
- `POST /admin/ebookslv/orders/api/<order_id>/refresh`
- `POST /admin/ebookslv/orders/api/import_paid`
- `DELETE /admin/ebookslv/orders/api/<order_id>`

Implementation: [app/routes/admin_ebookslv.py](app/routes/admin_ebookslv.py)

### 1.2 What “manual link user ↔ book” means

The current system grants access through **Mozello order records**, not a separate allow-list UI.

A “manual link” is implemented by creating an order record containing:
- `email` (normalized)
- `mz_handle` (Mozello product handle; typically `book-<calibre_id>`)

Link resolution happens by lookups:
- `mz_handle` → Calibre `book_id` via `books_sync.lookup_books_by_handles()`
- `email` → Calibre `user_id` via `calibre_users_service.lookup_user_by_email()`

These resolved IDs are stored back into the order record (`calibre_book_id`, `calibre_user_id`) for faster reads.

Implementation:
- [app/services/orders_service.py](app/services/orders_service.py)
- [app/services/books_sync.py](app/services/books_sync.py)
- [app/services/calibre_users_service.py](app/services/calibre_users_service.py)

---

## 2) Order record lifecycle

### 2.1 List and reconcile
`orders_service.list_orders()` returns:
- list of order view rows
- summary counts

It also performs reconciliation:
- loads current book mapping by handle and user mapping by email
- if the stored IDs drift, it issues `users_books_repo.bulk_update_links(updates)`

### 2.2 Create order (manual)
`orders_service.create_order(email, mz_handle)`:
- normalizes email
- looks up book by handle
- looks up user by email
- creates row in users_books DB via `users_books_repo.create_order(...)`

Error cases surfaced to UI:
- missing email → `email_required`
- missing handle → `mz_handle_required`
- duplicates → `order_exists`

### 2.3 Refresh
`orders_service.refresh_order(order_id)`:
- redoes handle/email lookups
- updates stored links if changed

### 2.4 Delete (revoking access)
`orders_service.delete_order(order_id)`:
- deletes the local order record only
- does not call Mozello

Net effect:
- Reader access is removed because the user no longer has a purchase record for that handle/book.

---

## 3) User creation and linking

### 3.1 Create/link user for an order
`orders_service.create_user_for_order(order_id)`:
- if a user already exists for that email:
  - links the order to the existing user
  - returns status `linked_existing`
- otherwise:
  - creates a Calibre user via `calibre_users_service.create_user_for_email(...)`
  - uses the book language (if known) as a language hint
  - links the order to the newly created user

Returned payload includes:
- `user` (Calibre user info)
- `password` (only if newly created)

### 3.2 There is no custom “delete user” endpoint

ebooks.lv does not currently expose a dedicated custom endpoint/UI to delete Calibre users.

If you must delete a user account:
- use Calibre-Web’s built-in admin user management UI (upstream)

Important operational note:
- If the user still has order records for their email, the next “Create User” action may create a new account again.

---

## 4) Password reset and first login

Password reset and first-login are implemented via the `/login` override.

Key mechanisms:
- `password_reset_service.issue_initial_token(email, temp_password, book_ids)`
  - used when a user is created during purchase provisioning
- `password_reset_service.issue_reset_token(email)`
  - used for standard “Forgot password?”

Tokens are encrypted payloads; persistence is tracked in `reset_passwords_repo`.

Full operator-facing flow is documented in:
- [docs/mozello_purchase_login_flow.md](docs/mozello_purchase_login_flow.md)

Implementation:
- [app/routes/login_override.py](app/routes/login_override.py)
- [app/services/password_reset_service.py](app/services/password_reset_service.py)
- [app/services/auth_link_service.py](app/services/auth_link_service.py)

---

## 5) Reader access computation

Access is computed per request by combining:
- purchased book IDs derived from order records
- free book IDs derived from Calibre `mz_price`

Implementation:
- [app/services/catalog_access.py](app/services/catalog_access.py)

---

## 6) Mozello import/webhook linkage (context)

How purchases arrive:
- Webhook endpoint: `/mozello/webhook` (Mozello notifications)
- Orders admin also supports manual import of paid orders via Mozello API.

Mozello API behavior details:
- [ .github/instructions/mozello_store_api.md ](.github/instructions/mozello_store_api.md)
