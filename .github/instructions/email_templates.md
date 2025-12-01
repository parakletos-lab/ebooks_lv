# Email Templates Reference

Source of truth for ebooks.lv admin email templates served under `/admin/ebookslv/email-templates/`.

## Storage
- All HTML lives in the `email_templates` table inside the `users_books` SQLite database.
- Access and mutations **must** go through `app.services.email_templates_service` (and the `/admin/ebookslv/email-templates` UI). Do not write raw SQL or bypass the service/repository pair.

## Template keys & tokens
Each template exposes a fixed set of placeholder tokens. Editors can insert tokens via the UI; application code must only rely on the tokens listed here.

| Template key      | Description                     | Tokens |
|-------------------|---------------------------------|--------|
| `book_purchase`   | Purchase confirmation e-mail    | `{{user_name}}`, `{{shop_url}}`, `{{my_books}}`, `{{books}}` |
| `password_reset`  | Password reset instructions     | `{{user_name}}`, `{{new_password_url}}` |

### Token details

- `{{shop_url}}` – Public Mozello storefront base URL.
- `{{my_books}}` – Login-protected link to the user's purchased catalog.
- `{{books}}` – HTML `<ul>` list of purchased titles with per-book login links.
- `{{new_password_url}}` – One-time login link generated for password reset requests.

### Subjects

- Each template stores a subject per language. When blank, the UI falls back to the template key title case.
- Updating subjects must still go through `app.services.email_templates_service.save_template` (exposed via the admin UI).

Add new template metadata here first, then wire up `app.services.email_templates_service` before exposing it in the UI.
