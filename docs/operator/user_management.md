# User Management

This is a simplified runbook for day-to-day user support.

You will mostly use **Mozello Orders** admin:

- Orders page: [/admin/ebookslv/orders/](/admin/ebookslv/orders/)

---

## 1) What you can do here

From the Orders page you can:

- Import paid orders from Mozello (to grant access)
- Add a manual order record (to grant access)
- Create (or link) a Calibre user for a customer
- Refresh an order record (re-check book/user links)
- Delete an order record (revokes access in ebooks.lv; does NOT change Mozello)

---

## 2) Common tasks

### 2.1 Customer bought a book but can’t see it

1. Open [/admin/ebookslv/orders/](/admin/ebookslv/orders/).
2. Click **Import paid Mozello orders**.
   - Use the date range (default is last ~10 days).
3. Find the customer row by **Email**.
4. If **Calibre book** is red / missing, click **Refresh** on that row.
5. If **Calibre user** is “Not linked”, click **Create User**.
   - If a user already exists, it will link instead of creating a new one.

Result:
- The order row should show a green **Calibre book** and a green **Calibre user**.

### 2.2 Manually grant access (create a manual user ↔ book link)

Use this when a customer paid but the webhook/import is missing, or for manual support cases.

1. Open [/admin/ebookslv/orders/](/admin/ebookslv/orders/).
2. In **Add Order** form:
   - Enter the customer **Email**.
   - Enter the **Mozello handle** for the purchased book.
     - Usually the handle looks like `book-123`.
3. Click **Add Order**.
4. If the row shows “Not linked” under **Calibre user**, click **Create User**.
5. If the row shows “Calibre book missing”, click **Refresh**.

Notes:
- If you don’t know the handle, open [/admin/ebookslv/books/](/admin/ebookslv/books/) and use the table to find the book and its Mozello handle.

### 2.3 Customer cannot log in / forgot password

Ask the customer to use the **Forgot password?** button on [/login](/login).

If email sending is configured, they will receive a password reset email.

If they still cannot reset:
- Confirm their email is correct in the order record.
- If needed, use **Create User** on their order row to ensure the account exists.

#### Password rules (important for browser-generated passwords)

If a customer uses a browser “suggested password” and it gets rejected, the rejection comes from Calibre-Web’s **User Password policy** settings.

Where to configure:
- [/admin/config](/admin/config) → **Edit Basic Configuration** → **User Password policy** section.

Settings that control validation:
- **User Password policy** (on/off). If OFF, Calibre-Web accepts any password (no policy checks).
- **Minimum password length** (`config_password_min_length`).
- **Enforce number** (`config_password_number`).
- **Enforce lowercase characters** (`config_password_lower`).
- **Enforce uppercase characters** (`config_password_upper`).
- **Enforce special characters** (`config_password_special`).

Recommended settings to accept typical browser-generated passwords:
- Keep **User Password policy = ON**
- Set **Minimum password length** to `12` (or `10` if you prefer)
- Enable **Enforce number / lowercase / uppercase**
- Disable **Enforce special characters** (many browsers don’t always include symbols in their suggested password)

If you want “accept anything the browser suggests” with the least surprises:
- Set **User Password policy = OFF**

### 2.4 Revoke access (remove a purchased book from a user)

1. Open [/admin/ebookslv/orders/](/admin/ebookslv/orders/).
2. Find the order record row.
3. Click the trash icon (**Delete**) and confirm.

Important:
- This deletes the **local access record** only.
- It does **not** refund or modify anything in Mozello.

### 2.5 Clean up duplicates / wrong email

- If an order row was created with the wrong email or handle, **Delete** it and create a new one.
- If multiple duplicates exist for the same user and handle, delete the extra ones.

---

## 3) Quick troubleshooting

### 3.1 “Calibre book missing”

Most common causes:
- The Mozello handle does not match any exported book.
- The book exists in Mozello but was never exported from our Books Sync tool.

Fix:
- Go to [/admin/ebookslv/books/](/admin/ebookslv/books/) and export/sync the book so the handle exists.
- Return to Orders and click **Refresh**.

### 3.2 “Create User” fails

Most common causes:
- Calibre runtime is unavailable.

Fix:
- Retry later.
- If the user already exists, try clicking **Reload** on the Orders page and then **Create User** again (it may link existing).

---
