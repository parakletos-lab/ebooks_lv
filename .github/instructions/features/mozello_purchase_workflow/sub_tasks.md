# Mozello Purchase Workflow – Detailed Sub-Tasks

Global constraints:
- Reuse Calibre-Web's existing `SECRET_KEY` as the encryption root; do **not** add a new `EBOOKSLV_AUTH_SECRET` env var.
- The `/login` override must support admins and regular users identically and maintain the existing session semantics so every downstream Calibre flow continues to work.
- Rename the email template label to "Book purchase" everywhere it is rendered.
- Preserve cache invalidation, logging, and configuration rules described in `AGENTS.md`.

## T1. Data & Credential Storage Foundations
**Goal:** capture per-user temporary passwords securely and prepare repository helpers for cleanup.

Implementation notes:
1. Extend `app/db/models/users_books.py` with a `ResetPasswordToken` table containing `id`, `email`, `password_hash`, `token_type` (`"initial"|"reset"`), `created_at`, `last_sent_at`, and indexes on `(email, token_type)`.
2. Add `app/db/repositories/reset_passwords_repo.py` with helpers to upsert a token, fetch by email/type, delete a row, and purge rows older than 30 days.
3. Ensure `app/db/engine.py` picks up the metadata so SQLite migrations happen automatically, and add a best-effort pruning step inside repository code.
4. Update `app/services/calibre_users_service.py` with a reusable `update_user_password(user_id, plaintext)` helper that hashes passwords with the same mechanisms as creation.

Testing:
- Unit-test repo helpers for create/read/delete/purge logic using the in-memory SQLite setup.
- Verify that password updates change the stored hash and respect helper validations.

## T2. Auth Link and Password Reset Services
**Goal:** centralize encryption/validation for auth links and manage password lifecycle rules.

Implementation notes:
1. Introduce `app/services/auth_link_service.py` leveraging Fernet (already supplied by `cryptography`) seeded from Flask's `SECRET_KEY`. Provide `encode_payload(payload_dict)` and `decode_payload(token)` with clear error handling for tampering.
2. Payload schema: `{ "email": str, "temp_password": Optional[str], "book_ids": List[int], "issued_at": iso }`. Purchase tokens must remain valid until explicitly cleared; reset tokens expire after 24h (validate timestamps on decode).
3. Add `app/services/password_reset_service.py` that coordinates with the new repository to:
   - Record temp passwords for new users without expiring them until the user sets a new password.
   - Generate reset tokens (email only) that automatically expire after 24h.
   - Delete tokens once consumed, and optionally offer a manual purge API.
4. Expose helpers for the login route: `resolve_pending_reset(email, token)` and `complete_password_change(email, new_password)`.

Testing:
- Unit-test round trips for auth-link encoding/decoding, including tampered tokens and expiry handling.
- Verify password-reset helper behavior (initial vs reset) and cleanup logic.

## T3. Email Template and Subject Editor Upgrades
**Goal:** allow editors to manage per-language subjects and new token sets from the admin UI.

Implementation notes:
1. Modify `email_templates` schema via SQLAlchemy model to include a `subject` column (non-null, default empty string).
2. Update `email_templates_service` to surface both `subject` and `html_body`, plus validation ensuring single-line subjects.
3. Adjust `/admin/ebookslv/email-templates` UI:
   - For each language tab, add a subject `<input type="text">` above the WYSIWYG field.
   - Ensure switching languages updates both subject and body inputs.
4. Rename the template label from "Book purchase e-mail" to "Book purchase" in all metadata.
5. Update template metadata/tokens so `book_purchase` exposes `{{user_name}}`, `{{shop_url}}`, `{{my_books}}`, and `{{books}}`. Remove obsolete tokens from the UI listing to avoid confusion.

Testing:
- Add service-level tests to ensure subjects persist per language and are returned via the API.
- Exercise the admin endpoints with Flask test client to confirm save/list flows handle the new fields.

## T4. Mozello Webhook and Email Dispatch Workflow
**Goal:** generate multi-book purchase emails and drive the reader redirects without adding environment knobs.

Implementation notes:
1. Enhance `orders_service.process_webhook_order` so each Mozello `cart` entry contributes to the `{{books}}` HTML list (link to `/book/<id>` using Calibre ID and title).
2. Compute supporting tokens:
   - `{{shop_url}}`: base Mozello store URL from settings (`mozello_service.get_store_url()`).
   - `{{my_books}}`: absolute URL to the Calibre "My books" page (`/catalog/my-books`).
3. Build the `book_reader_url` logic into the new email-delivery helper, generating `/login?next=/book/<id>&auth=<token>` per user/book.
4. Create `app/services/email_delivery.py` that fetches template subject/html, renders tokens, and queues HTML+text emails via a specialized TaskEmail subclass. Fail fast if SMTP is misconfigured.
5. Remove the old Calibre-native password reset email from the webhook path; rely entirely on our templated notifications.

Testing:
- Add service tests validating token substitution (especially the `{{books}}` list) using fixture data.
- Integration-test the webhook handler with a sample payload to ensure email-delivery helpers are invoked and reset tokens are recorded.

## T5. Login Override UX and Session Handling
**Goal:** replace `/login` end-to-end with email-based auth while preserving Calibre functionality.

Implementation notes:
1. Register a new blueprint (e.g., `login_override_bp`) that handles both GET and POST on `/login` before Calibre's default route.
2. The form must always show Email + Password inputs, with conditional UI for:
   - Forced password creation (two new-password fields) when an auth token carries `temp_password`.
   - Forgot-password mode triggered via dedicated button (no separate admin link needed).
3. Authenticate users by email: look up the associated Calibre username, verify the password hash, call `login_user`, and set the same session keys (`user_id`, `session_email_key`) the original implementation used.
4. When completing a password creation/reset, update the Calibre hash via `calibre_users_service.update_user_password`, delete the stored token, and auto-login the user.
5. Sanitize `next` redirects using Calibre's existing helper or a local equivalent to prevent open redirects.

Testing:
- Write Flask test-client cases covering: normal login, bad password, forgot-password success/failure, forced password change via auth token, and redirect handling.
- Smoke-test that authenticated sessions can access catalog pages and purchase-only content.

## T6. Documentation and Automated Tests
**Goal:** capture the full flow for future operators and ensure regressions are caught.

Implementation notes:
1. Author `docs/mozello_purchase_login_flow.md` (or reuse existing docs folder) describing the purchase→email→login sequence, including the new token semantics and the absence of token expiry for initial purchases.
2. Update `.github/instructions/email_templates.md` with the new subject field behavior and revised token list.
3. Document the plan usage (this folder) and remind contributors to update `index.md` statuses as they land code.
4. Expand the automated test suite to cover all new services and routes introduced earlier; aim for meaningful coverage around encryption, repository persistence, and HTTP endpoints.

Testing:
- Run targeted unit tests plus existing suites; document any manual QA required (e.g., Mozello webhook replay) inside the new doc.

---
When finishing a sub-task, update `index.md` with the new status and briefly note the verifying commit hash for traceability.
