# E2E: users_books Admin Page

Goal: Validate the allow‑list admin UI at `/admin/users_books` renders correctly and core operations (list + add + delete) function.

## Preconditions
- Container rebuilt after any template/route change:
	- `docker compose up -d --build calibre-web-server`
- Admin user logged in (session valid).

## 1. Page Renders & CSRF Present
1. Navigate to `/admin/users_books`.
2. View page source (or DOM snapshot) and assert hidden CSRF input exists: `input#ub-csrf[name="csrf_token"][value != ""]`.
3. Assert main structural elements exist:
	 - `#ub-users-box`, `#ub-books-box`, `#ub-mappings-tbody`, `#ub-log`.

## 2. Users List Populated
1. Wait for initial log to include `Users loaded:`.
2. Assert `#ub-users-box label` count > 0.
3. (Optional filter test) Type a substring of a known email in `#ub-filter-users`; ensure non‑matching labels hide.

## 3. Books List Populated
1. Wait for log to include `Books loaded:`.
2. Assert `#ub-books-box label` count > 0.
3. Filter via `#ub-filter-books`; confirm filtering behavior.

## 4. Mappings Table Populated (or Empty State)
1. Wait for log line `Mappings loaded:`.
2. If count > 0 in log, assert `#ub-mappings-tbody tr` contains matching number of delete buttons (`button[data-del]`).
3. If count = 0, verify single row with text `No mappings present.`

## 5. Add Mapping Flow
Purpose: create a new user↔book pair not currently in mappings.
1. Pick one user checkbox (value=U) not mapped yet to book B; pick one book checkbox (value=B) likewise.
2. Click `#ub-add-mappings`.
3. Observe log lines containing pattern `u=U b=B -> added` or `exists` (added is expected for a new pair).
4. After "Add operations complete." wait for automatic `Mappings loaded:` refresh.
5. Assert a row now exists with `data-del="U:B"`.

## 6. Delete Mapping Flow
1. Click the delete button whose `data-del="U:B"`.
2. In confirm dialog: accept.
3. Log should show `Deleting mapping user=U book=B...` then `Delete status: deleted`.
4. After refresh, assert button with `data-del="U:B"` no longer present.

## 7. Negative / Edge Checks (Optional)
- Attempt to add same mapping again: expect `exists` status, no duplicate row.
- Delete a non‑existent mapping via direct fetch: expect JSON `not_found`.

## 8. Automation Selector Summary
- Users: `#ub-users-box input[type=checkbox]`
- Books: `#ub-books-box input[type=checkbox]`
- Add button: `#ub-add-mappings`
- Refresh mappings: `#ub-reload-mappings`
- Mappings rows delete buttons: `#ub-mappings-tbody button[data-del]`
- Log: `#ub-log`

## 9. Minimal Script Snippets (Reference)
Add (browser console):
```
// Assumes first user & book
const u = document.querySelector('#ub-users-box input[type=checkbox]').value;
const b = document.querySelector('#ub-books-box input[type=checkbox]').value;
document.getElementById('ub-add-mappings').click();
```
Delete:
```
const btn = document.querySelector('#ub-mappings-tbody button[data-del]');
if(btn) btn.click();
```

## 10. Pass Criteria
- CSRF input present & non-empty.
- Users & books > 0.
- Mapping add shows expected log and row appears.
- Mapping delete returns 200, removes row, log shows `deleted`.

---
Keep this file concise; expand only if new behaviors are added.
