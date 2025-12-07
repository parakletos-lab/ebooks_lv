# ebooks.lv App Translation Checklist (lv / ru / en)

Objective: ensure every user-facing string in our first-party app is available
in Latvian, Russian, and English. Source strings should remain in English;
translations live under `translations/ebookslv/<locale>/LC_MESSAGES/messages.po`.

## Templates (Jinja + inline JS)
- `app/templates/layout.html` (nav injection fallback `<script>` still hardcodes `ebooks.lv` label)
- `app/templates/login_override.html` (all form/CTA strings wrapped in `_()` and synced to lv/ru catalogues)
- `app/templates/ebookslv_admin.html` (UI cards + JS status strings localized via injected dict)
- `app/templates/orders_admin.html` (table headers + inline JS alerts/prompts translated; lv/ru done)
- `app/templates/ebookslv_books_admin.html` (page title, buttons, table headers remain English)
- `app/templates/ebookslv_books_admin.html` inline JavaScript tooltips/log messages (hundreds of literal strings)
- `app/templates/email_templates_admin.html` (tab labels, button text, status copy, token labels)
- `app/templates/mozello_admin.html` (form labels, helper text, alert strings)
- `app/templates/users_books_admin.html` (section legends, helper paragraphs, button text, JS warnings)
- `app/templates/stats.html` (Calibre attribution notice + final table note not wrapped in `_()` yet)
- `app/templates/non_admin_catalog.html` (public catalog override snapshot is English-only; gate or localize before enabling)

## Flask views / responses (Python strings wrapped in `_()`)
- `app/routes/admin_ebookslv.py` (JSON errors return English keys like `order_exists`, `book_not_found`)
- `app/routes/admin_mozello.py` (error payloads + webhook reasons need translation or mapping)
- `app/routes/admin_users_books.py` (REST messages such as "book_ids must be..." returned to UI)
- `app/routes/login_override.py` (form validation errors + flash messages still literal English strings)
- `app/routes/health.py` (status text ok for ops, skip unless exposed to end users)

## Navigation / runtime DOM injections
- `app/templates/layout.html` + loader/after-request nav injection (ensure injected `<li>` labels go through translations or locale payload)
- `app/routes/overrides/nav_injection.py` (mirrors layout script; consolidate with translations once strings extracted)
- `app/routes/overrides/catalog_access.py` payload consumed by `non_admin_catalog.js` (feeds `buy_label`, `My Books` copy)
- `app/routes/overrides/stats_notice.py` (injected `<small>` text should use `_()` and re-render per locale)

## Services / jobs emitting user-visible text
- `app/services/email_delivery.py` (fallback subjects like "Your ebooks are ready" / "Reset your password")
- `app/services/email_templates_service.py` (template labels/descriptions + token labels powering the admin UI tabs)
- `app/services/orders_service.py` (API error codes such as `email_required`, `invalid_date_range` surfaced directly)
- `app/services/mozello_service.py` (API error strings bubbled to admin UI)
- `app/services/books_sync.py` (warnings shown in UI/logs and via admin pages)
- `app/services/password_reset_service.py` (user notifications + exception messages hitting UI)

## Email template content (DB-backed)
- `/admin/ebookslv/email-templates` UI entries for each template must have
      lv/ru/en variants (per `.github/instructions/email_templates.md`). No ru/en rows exist yet.

## Static assets embedding text
- `app/static/ebookslv_admin.css` (no `content:` or hardcoded language detected after audit)
- `app/static/catalog/non_admin_catalog.js` (`My Books`, `Buy Online`, tooltip strings currently literal)
- Remaining inline `<script>` blocks outside `orders_admin.html` (books admin, email templates, Mozello, users_books) still emit plain-English alerts/tooltips; port to `_()` JSON payloads.

## Verification
- Run `pybabel extract`/`update` for the `ebookslv` domain.
- Compile `messages.mo` for lv, ru, en.
- Test locale switch (per Calibre user preferences) across admin
      pages, login override, and Mozello purchase flow. Use Playwright MCP to test it in browser. (admin@example.org/AdminTest123!)
