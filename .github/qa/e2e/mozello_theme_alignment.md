# E2E: Mozello-aligned Theme (UI)

Goal: Calibre-Web UI should visually align with the Mozello shop header/buttons (see issue #11 screenshots).

## Preconditions
- Containers are running: `bash .github/qa/scripts/run_all.sh`
- Base URL: `http://localhost:8083`

## Checks (Anonymous)
- Open `/` and confirm:
  - Header brand uses **Poppins** (or falls back to Arial/Helvetica) and looks like Mozello style.
  - Brand shows the ebooks.lv logo **above** the title.
  - Navbar has square corners (no rounded top/borders).
  - Nav links are uppercase; active link has green underline.

## Checks (Login page)
- Open `/login` and confirm:
  - The login panel/card is squared (no rounded corners) and flat (no shadow).
  - The "Aizmirsi paroli?" control looks like a link (not a padded button).

## Checks (Non-admin)
- Login as non-admin (`qa_user` from QA output) and open `/`.
- Confirm:
  - Search input and buttons have **no rounded corners**.
  - Primary buttons are green; default buttons are white with green border.

## Checks (Non-admin catalog buy actions)
- On catalog grid, find a book that is not purchased/free.
- Confirm:
  - The “buy” badge is square/flat.
  - The cart icon is the **SVG cart** (not the Bootstrap glyphicon font).
  - Hovering the cart triggers a small "zoom" animation.
- Open a book detail page and confirm:
  - The injected “Buy Online” button shows the SVG cart icon and uses the Mozello-aligned button styling.
