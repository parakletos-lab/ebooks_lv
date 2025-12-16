# E2E: Anonymous cannot access Discover (Random Books)

Target: local dev container at `http://localhost:8083`.

## 0) Preconditions
- Run: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Ensure anonymous access is enabled in calibre-web settings if you want to validate the anonymous UI.

## 1) Anonymous sidebar
1. Open `/` without logging in.
2. In the left sidebar (`#scnd-nav`), assert the Discover link is NOT present:
   - `#nav_rand` should not exist.

## 2) Anonymous direct access
1. Directly open `/discover/stored`.
2. Expect redirect to `/` (or the index page).

## 3) Authenticated user
1. Login as a normal user.
2. Open `/discover/stored`.
3. Expect page to render (status 200) and show random books.
