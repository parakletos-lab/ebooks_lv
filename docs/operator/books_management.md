# Books Management (Operator)

This is a simplified runbook for day-to-day book management.

You will work in two places:

- **Calibre** (where book files and book details live)
- **ebooks.lv Admin → Books Sync** ([/admin/ebookslv/books/](/admin/ebookslv/books/)) (where you push/sync to Mozello)

---

## 1) Where to click

- Books Sync page: [/admin/ebookslv/books/](/admin/ebookslv/books/)
- Mozello settings page (API key, webhook): [/admin/ebookslv/mozello/](/admin/ebookslv/mozello/)

Buttons you will use on the Books Sync page:

- **Reload Calibre Books**
- **Push Prices to Mozello**
- **Sync Prices from Mozello**
- **Load Mozello Products**
- **Export All to Store**
- **Delete** (per product)

---

## 2) Common tasks

### 2.1 Add a new paid book

1. Add the book in **Calibre** and fill in the book details (title, cover, description, language).
2. Set the **price** in Calibre (use the field named `mz_price`).
   - Price must be **greater than 0**.
3. Open [/admin/ebookslv/books/](/admin/ebookslv/books/).
4. Click **Reload Calibre Books**.
5. Export to Mozello:
   - Click **Export All to Store**.
6. Confirm it worked:
   - Use **LV / RU / EN** buttons to open the Mozello product page.

### 2.2 Change a price (Calibre → Mozello)

Use this when you want Calibre to be the final price.

1. Change the price in Calibre (`mz_price`).
2. Open [/admin/ebookslv/books/](/admin/ebookslv/books/).
3. Click **Push Prices to Mozello**.

### 2.3 Change a price (Mozello → Calibre)

Use this if someone changed the price directly in Mozello.

1. Open [/admin/ebookslv/books/](/admin/ebookslv/books/).
2. Click **Sync Prices from Mozello**.

### 2.4 Make a paid book free

1. In Calibre set the price (`mz_price`) to **0** (or clear it).
2. Decide if you still want the Mozello product to exist:
   - If you do NOT want it sold anymore: on [/admin/ebookslv/books/](/admin/ebookslv/books/) click **Delete** for that product.

### 2.5 Delete a Mozello product

1. Open [/admin/ebookslv/books/](/admin/ebookslv/books/).
2. Click **Delete** for the product.

---

## 3) Orphans (Mozello product without a matching book)

1. Click **Load Mozello Products**.
2. Rows marked **ORPHAN** are products that exist in Mozello but don’t match a book.
3. Usually the safe action is **Delete** the orphan, then export the correct book from Calibre.

---

## 4) Quick troubleshooting

### 4.1 Export fails

- Check Mozello settings at [/admin/ebookslv/mozello/](/admin/ebookslv/mozello/).
- Try exporting again to see the error.

### 4.2 LV/RU/EN product links fail

- Click **Load Mozello Products** and retry.
- If still failing, retry export.

---
