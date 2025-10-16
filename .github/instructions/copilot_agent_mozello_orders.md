# Refactor and extend admin functionality for Mozello order integration.

## Tasks

### 1. Refactor existing page and services
- Refactor `/admin/ebookslv/users_books/` page, related table, and services to clean structure and prepare for reuse.
- The current page includes controls and backend services that allow manually adding `users_books` records — these should be **kept**, but **updated or adjusted as needed** to stay compatible with the new logic.
- The `users_books` feature is **not in production**, so **no data migration is required** — feel free to modify both the code and the database schema as needed.

### 2. Create new “Orders” page
- Add new route `/admin/ebookslv/orders/` and navigation link labeled **Orders**.
- This page **replaces the old users_books page now**.

### 3. Orders management logic
- Each record should contain:
  - `email` (required)
  - `mz_handle` (required)
- Combination of `email + mz_handle` must be unique.
- These fields can be filled manually or via Mozello webhook/import **(note: actual webhook code and manual Mozello orders sync are out of scope for now).**

### 4. Validation & linkage
- When saving a record:
  - If a Calibre book with the given `mz_handle` **exists**, link it.
  - If it **does not exist**, still create the record, but on the page display an **error message instead of the Calibre book name**.
  - Check if a Calibre user with the same email exists:
    - If not, display a **Create User** button (manual action).
    - Also prepare service support to create users automatically when webhook runs later.

### 5. Table display
- Columns:
  - `mz_handle`
  - `Calibre book name` (or error message if missing)
  - `email`
  - `Calibre user name` (or button to create)
- Data source should use the updated `users_books` table holding imported Mozello orders.

### 6. Services
- Add or refactor service to create a Calibre user by email.
- Ensure the service can be triggered both manually and from webhook later.

### 7. Implementation
- Implement immediately.
- Reference existing admin pages and services for structure and style.
- If something in this description is missing or inconsistent, use the most reasonable and maintainable solution following existing project conventions.
- We’ll test after implementation.
