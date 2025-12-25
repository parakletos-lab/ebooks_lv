# RU tooltips translation (Calibre-Web)

Goal: ensure common UI tooltips are localized when `RUS` is active.

## Preconditions
- Run dev stack: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- Log in as admin (default dev bootstrap): `admin@example.org / AdminTest123!`

## Steps
1. Open `/` and switch language to `RUS` using the header buttons.
2. On the main catalog page, hover the sorting buttons (icons row). Verify tooltips are Russian, e.g.:
   - Book date: newest/oldest
   - Title: A→Я / Я→А
   - Author: A→Я / Я→А
   - Publishing date: newest/oldest
3. Open `/hot/stored/` and hover the two sort buttons. Verify tooltips are Russian:
   - Download count ascending/descending
4. Open a book details page (e.g. `/book/5`). Hover:
   - `Read` control tooltip (“mark as read/unread”)
   - `Archive` control tooltip (long archive explanation)
   Verify both are Russian.
5. (Optional) Create a shelf and add a book to it, then open the shelf page and hover the shelf sorting buttons:
   - Added-to-shelf newest/oldest tooltips are Russian.

## Expected
No English tooltip strings remain for the controls above while `RUS` is active.
