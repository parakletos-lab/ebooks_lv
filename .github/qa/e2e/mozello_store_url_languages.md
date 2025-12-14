# E2E: Mozello Store URL per Language (LV/RU/EN)

Target: local dev container at `http://localhost:8083`.

## Preconditions
- Container rebuilt after template/route change:
  - `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Admin user logged in (session valid).

## 1) Page renders + language tabs
1. Open `/admin/mozello/`.
2. In "Mozello Settings" panel, find the language tabs next to "Mozello Store URL": `LV`, `RU`, `EN`.
3. Click `LV`, `RU`, `EN` and confirm each shows its own input field.

## 2) Save all three URLs
1. Enter distinct values:
   - LV: `https://lv.example.test/store`
   - RU: `https://ru.example.test/store`
   - EN: `https://en.example.test/store`
2. Click **Save Settings**.
3. Click **Reload** and confirm the three values persist.
4. Hard refresh the page and confirm the three values persist.

## 3) Redirect uses current user language
1. Switch UI language to `RU` (via the site language switch).
2. Navigate to `/mozello/books/<known-handle-or-book-id>`.
3. Confirm the redirect target base URL starts with the RU store URL (`https://ru.example.test/store`).
4. Repeat for `LV` and `EN`.

## Pass Criteria
- All 3 URLs save and reload correctly.
- Mozello product redirect uses the active session/UI language store URL.
# E2E: Mozello Store URL per Language (LV/RU/EN)

Target: local dev container at `http://localhost:8083`.

## Preconditions
- Container rebuilt after template/route change:
  - `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Admin user logged in (session valid).

## 1) Page renders + language tabs
1. Open `/admin/mozello/`.
2. In "Mozello Settings" panel, find the language tabs next to "Mozello Store URL": `LV`, `RU`, `EN`.
3. Click `LV`, `RU`, `EN` and confirm each shows its own input field.

## 2) Save all three URLs
1. Enter distinct values:
   - LV: `https://lv.example.test/store`
   - RU: `https://ru.example.test/store`
   - EN: `https://en.example.test/store`
2. Click **Save Settings**.
3. Click **Reload** and confirm the three values persist.
4. Hard refresh the page and confirm the three values persist.

## 3) Redirect uses current user language
1. Switch UI language to `RU` (via the site language switch).
2. Navigate to `/mozello/books/<known-handle-or-book-id>`.
3. Confirm the redirect target base URL starts with the RU store URL (`https://ru.example.test/store`).
4. Repeat for `LV` and `EN`.

Pass criteria:
- All 3 URLs save and reload correctly.
- Mozello product redirect uses the active session/UI language store URL.
