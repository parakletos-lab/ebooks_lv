# Email Templates Reference

Source of truth for ebooks.lv admin email templates served under `/admin/ebookslv/email-templates/`.

## Storage
- All HTML lives in the `email_templates` table inside the `users_books` SQLite database.
- Access and mutations **must** go through `app.services.email_templates_service` (and the `/admin/ebookslv/email-templates` UI). Do not write raw SQL or bypass the service/repository pair.

## Template keys & tokens
Each template exposes a fixed set of placeholder tokens. Editors can insert tokens via the UI; application code must only rely on the tokens listed here.

| Template key      | Description                     | Tokens |
|-------------------|---------------------------------|--------|
| `book_purchase`   | Purchase confirmation e-mail    | `{{user_name}}`, `{{book_title}}`, `{{book_shop_url}}`, `{{book_reader_url}}` |
| `password_reset`  | Password reset instructions     | `{{user_name}}`, `{{new_password_url}}` |

Add new template metadata here first, then wire up `app.services.email_templates_service` before exposing it in the UI.
