# Mozello Purchase → Login Flow

This guide describes the end-to-end experience customers follow after purchasing a book on the Mozello shop. Share it with operators when validating deployments or training support staff.

## 1. High-level sequence

1. **Purchase completes on Mozello.** The webhook payload is delivered to `/admin/mozello/webhook`.
2. **Orders service validates the payload** and records the purchased Calibre book IDs. The service creates or reuses the Calibre-Web user for the buyer.
3. **Email delivery renders the “Book purchase” template.** Each title is turned into a `<li>` entry that links to `/login?next=/book/<id>&auth=<token>` so readers jump directly into the secure catalog after signing in.
4. **The customer opens the email,** clicks any book link, and lands on the `/login` override UI.
5. **Login override handles authentication** for both admins and regular users:
   - If an initial token contains a temporary password, the page prompts for the new password twice and logs the user in after saving the Calibre hash.
   - Otherwise, users can sign in with their existing password or choose “Forgot password?” to request a reset link.
6. **Once signed in,** Calibre-Web redirects the user to either the requested book detail page or the default catalog.

## 2. Token semantics

| Token type | When issued | Expiry | Notes |
| --- | --- | --- | --- |
| Initial (`temp_password` present) | User created during a Mozello purchase | Never (until consumed) | Requires the user to set a permanent password before the session is fully active. |
| Reset (`temp_password` absent) | Via `/login` “Forgot password?” or admin-triggered reset | 24 hours | Stored in `reset_passwords_repo`; removed immediately after `complete_password_change` succeeds. |

All tokens are encrypted with Fernet derived from Calibre-Web’s `SECRET_KEY`. Never attempt to mint tokens outside `app/services/password_reset_service.py`.

## 3. Email templates & subjects

- The “Book purchase” and “Password reset” templates live in `users_books.email_templates` and are edited via `/admin/ebookslv/email-templates`.
- Each language stores both a subject and HTML body. Subjects must be plain text, one line, and are required for translation parity.
- Tokens available to editors: see `.github/instructions/email_templates.md` for the definitive list. (Keep that file updated when introducing new tokens.)

## 4. Operator playbook

### Rebuilding and testing locally

1. `bash scripts/dev_rebuild.sh` – Rebuild the docker stack so both Calibre-Web and the integrated app pick up code and template changes.
2. Visit `http://localhost:8083/login` to ensure the override UI renders.
3. Use Playwright MCP (Chrome DevTools profile) to run the following smoke script against the dockerized site:
   - Request reset tokens for an admin and a non-admin user with the inline helper below (run from the repo root):

    ```bash
    CALIBRE_DBPATH=$PWD/config PYTHONPATH=$PWD:$PWD/calibre-web:$PWD/app python - <<'PY'
    import os
    from flask import Flask
    from cps import ub, constants, config_sql
    from app.services import calibre_users_service, password_reset_service

    def issue(email: str):
       calibre_users_service.ub = ub
       app_db = os.path.join(constants.CONFIG_DIR, constants.DEFAULT_SETTINGS_FILE)
       if getattr(ub, 'session', None) is None:
          ub.init_db(app_db)
       secret = config_sql.get_flask_session_key(ub.session)
       app = Flask(__name__)
       app.config['SECRET_KEY'] = secret
       with app.app_context():
          user = calibre_users_service.lookup_user_by_email(email)
          if not user:
             print(f"missing user {email}")
             return
          token = password_reset_service.issue_reset_token(email=email)
          print(f"{email}:{token}")

    issue('admin@example.org')
    issue('qa_filter@example.test')
    PY
    ```
   - Load `/login?email=<user>&auth=<token>`, set a new password, verify redirect + flash “Password updated. You’re signed in.”
   - Log out and log back in with the fresh password to confirm standard authentication still works.

### Production validation checklist

- Mozello webhook logs show `orders_service` processed the most recent purchase (check `docker compose logs calibre-web`).
- `email_delivery` logs show the reset email queued with the expected language and book count.
- `/admin/ebookslv/email-templates` lists the “Book purchase” template with the updated subject + token descriptions.
- `/login` displays the ebooks.lv override UI (email-first) rather than the upstream username form.

## 5. Contributor reminders

- Keep `.github/instructions/features/mozello_purchase_workflow/index.md` up to date when completing tasks. Move the current task row to **Completed** only after the code, docs, and tests land on the branch.
- Whenever a new environment variable or service is introduced, document it in `AGENTS.md` and add accessors in `app.config`.
- Run the targeted pytest modules (`tests/routes/test_login_override.py`, `tests/services/test_password_reset_service.py`, `tests/services/test_email_delivery.py`) plus any new suites touching these flows before requesting review.

Maintaining this document alongside the instructions folder ensures future developers and operators share the same expectations for the Mozello → Calibre login journey.
