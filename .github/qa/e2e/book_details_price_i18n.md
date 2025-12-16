# Book details: Price + Read/Archive i18n

Goal: verify the **book details modal/page** shows translated labels and EUR price formatting.

## Bootstrap

```bash
docker compose -f compose.yml -f compose.dev.yml up -d --build
bash .github/qa/scripts/run_all.sh
```

Base URL: `http://localhost:8083`

## Non-admin (LV)

1) Login as non-admin user:
- `/login`
- Username: `qa_user`
- Password: `qa_user123`

2) Switch language to LV:
- Open: `/language/switch?lang=lv&next=/`

3) Open any book details (click a book cover/title).

Expected:
- Read checkbox label is `izlasīta`
- Archive checkbox label is `Arhivēta`
- If the book has `mz_price` set, the custom field shows `Cena: €X,YY` (comma decimals), e.g. `Cena: €6,50`

4) Check Hot Books title:
- Open `/hot/stored/`

Expected:
- Page heading uses: `Populārākās grāmatas (visvairāk lejupielādētās)`
- Left nav item for Read Books uses: `Izlasītas grāmatas`

## Non-admin (RU)

1) Switch language to RU:
- Open: `/language/switch?lang=ru&next=/`

2) Open any book details.

Expected:
- Read checkbox label is `Прочитана`
- Archive checkbox label is `В архиве`
- If the book has `mz_price` set, the custom field shows `Цена: €X,YY` (comma decimals)
