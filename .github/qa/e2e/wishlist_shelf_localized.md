````markdown
# E2E: Wishlist shelf created (localized) on Mozello webhook user creation

Goal: When Mozello webhook creates a **new** Calibre-Web user, ensure the user gets a wishlist shelf with a translated name based on user language.

## Preconditions
- Container running: `docker compose -f compose.yml -f compose.dev.yml up -d --build`
- You have a way to trigger a Mozello paid-order webhook that results in **new user creation** (new email).

## Expected shelf names
- LV: `Vēlmju saraksts`
- RU: `Список желаний`
- EN: `Wishlist`

## Steps (repeat per language)
1. Trigger a Mozello webhook paid order for a *new* email (so a new Calibre-Web user is created) where the resulting user language becomes LV/RU/EN.
2. Log in as that newly created user.
3. In the left sidebar under **Grāmatu plaukti / Bookshelves**:
   - Expect a shelf entry with the translated wishlist name.
4. Click the shelf.
   - Expect the page title/header to contain `Plaukts: '<translated name>'`.

## Pass Criteria
- The wishlist shelf exists immediately after first login.
- Shelf name matches expected translation for the user language.

````
