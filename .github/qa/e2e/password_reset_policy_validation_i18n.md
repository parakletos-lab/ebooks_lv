# Password reset: policy validation + i18n (regression)

Goal: ensure the `/login?auth=...` password reset page:
- receives the **real Calibre-Web password policy** flags (does not regress to zeros after refresh),
- shows **joined, red** client-side validation on blur,
- is **translated** when switching language (LAT/RUS).

## Preconditions

- Start QA stack:

```bash
docker compose -f compose.yml -f compose.dev.yml up -d --build calibre-web
```

- Ensure deterministic admin exists:

```bash
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web \
	python /app/.github/qa/scripts/bootstrap_admin.py
```

## Generate reset URL (in-container)

```bash
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web \
	python /app/.github/qa/scripts/bootstrap_admin_reset_token.py
```

- Tip: if you want just the URL:

```bash
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web \
   python /app/.github/qa/scripts/bootstrap_admin_reset_token.py \
| tail -n 1 | jq -r .url
```

- Open the returned URL in a browser.

## Checks (LV)

1. Click `LAT` language switch.
   - Expect `LAT` to be the active selection (highlighted).
2. Confirm the page title/header are Latvian.
3. Type `abc` into “Jauna parole” and blur (click into confirmation field).
4. Expect a single joined message (red), starting with:
   - `Parolei jābūt:`
5. Refresh the page and repeat step 3.
   - Expect the same kind of message again (proves policy flags still present after refresh).

## Checks (RU)

1. Click `RUS` language switch.
   - Expect `RUS` to be the active selection (highlighted).
2. Type `abc` into the new password field and blur.
3. Expect a single joined message (red), starting with:
   - `Пароль должен:`

## Optional: verify policy flags are present

View page source and confirm the new-password input includes non-zero `data-` attributes, e.g.:
- `data-policy-enabled="1"`
- `data-min-length="8"` (or your configured minimum)
