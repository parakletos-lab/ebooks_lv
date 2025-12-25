# Advanced Search: i18n (LV + RU)

Goal: verify **/advsearch** is fully localized for LV and RU, including the custom `Price` field label.

## Bootstrap

```bash
docker compose -f compose.yml -f compose.dev.yml up -d --build
bash .github/qa/scripts/run_all.sh
```

Base URL: `http://localhost:8083`

## Admin (LV)

1) Login as admin:
- `/login`
- Username: `admin@example.org`
- Password: `AdminTest123!`

2) Switch language to LV:
- Open: `/language/switch?lang=lv&next=/advsearch`

Expected on `/advsearch`:
- Custom field label shows `Cena`
- Price range labels use:
  - `No:`
  - `Līdz:`

Expected in browser console/network:
- No 404s for LV locale assets:
  - `bootstrap-datepicker.lv.min.js`
  - `defaults-lv.min.js`
- Multi-select placeholders show LV text (e.g. `Nekas nav atlasīts`)

## Admin (RU)

1) Switch language to RU:
- Open: `/language/switch?lang=ru&next=/advsearch`

Expected on `/advsearch`:
- `Read Status` label is localized (no English)
- `Exclude Shelves` label is localized (no English)
- Custom field label shows `Цена`

## Shelf page (RU)

1) Open shelf:
- `/shelf/3`

Expected:
- Buttons/labels are localized (no English):
  - `Edit Shelf Properties`
  - `Arrange books manually`
  - `Disable Change order`
