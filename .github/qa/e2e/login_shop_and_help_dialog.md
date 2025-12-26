````markdown
# E2E: Login shop link + help dialog

## Goal
Ensure the login override page shows:
- A bottom-right **Shop** link (localized) that navigates to the configured Mozello store URL for the currently selected language.
- A top-right square **?** icon button that opens a dialog with localized help text.

## Preconditions
- Local dev stack is running and rebuilt:

```bash
docker compose -f compose.yml -f compose.dev.yml up -d --build
```

- Mozello store URLs are configured (admin panel or seeded env) for LV/RU/EN.

## Steps
1. Open `http://localhost:8083/login`.
2. Confirm the **Shop** link is visible at the bottom-right of the login form.
3. Click the **Shop** link.

**Expected**
- It navigates to the Mozello store base URL matching the current UI language (lv/ru/en).

4. Return to `/login`.
5. Click the square **?** icon in the top-right of the login panel title.

**Expected**
- A dialog opens.
- Dialog body text matches the current UI language:

LV:
> Lai izveidotu savu lasītavas profilu, vispirms ir jāiegādājas grāmata e-books.lv veikalā. Bezmaksas grāmatas var lasīt bez reģistrēšanās.

RU:
> Чтобы создать профиль читателя, сначала необходимо приобрести книгу в магазине e-books.lv. Бесплатные книги можно читать без регистрации.

EN:
> To create your reader profile, you first need to purchase a book from the e-books.lv store. Free books can be read without registration.

6. Close the dialog with the close button.

**Expected**
- Dialog closes.

````
