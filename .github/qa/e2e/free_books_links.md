````markdown
# E2E: Free Links (Anon vs Logged-In)

Purpose: Ensure the Free scope is accessible to anonymous users and shows the correct CTA (Read, not Buy) for zero/missing price books, and that logged-in users also see read (not buy) for free items.

## Preconditions
- Container running locally with seeded data (`bash .github/qa/scripts/run_all.sh` to bootstrap users/orders).
- At least one Calibre book with `mz_price` missing or `0` so it is treated as free.

## Steps (Anonymous)
1. Open `/`.
2. Click "Free" nav link or open `/catalog/free-books`.
   - Expect no redirect to login; nav item is active.
3. Open a free book detail modal.
   - Assert "Read in Browser" button is present.
   - Assert there is no "Buy Online" button/badge.
4. Click "Read in Browser - epub".
   - Expect reader loads (no infinite spinner) and book content becomes visible.

## Steps (Logged-In Non-Admin)
1. Log in as seeded non-admin user (`QA_USER_USERNAME` / `QA_USER_PASSWORD`).
2. Open `/catalog/free-books`.
3. Open the same free book detail modal.
   - Assert "Read in Browser" button present.
   - Assert no "Buy Online" button/badge.
4. Click "Read in Browser - epub".
   - Expect reader loads (no infinite spinner) and book content becomes visible.

## Pass Criteria
- Free page accessible without login.
- Free book details show Read CTA and hide Buy for both anonymous and logged-in users.
- Reader works end-to-end for free books (epub loads; no hanging spinner).
- No console errors when opening Free scope and book modal.
````