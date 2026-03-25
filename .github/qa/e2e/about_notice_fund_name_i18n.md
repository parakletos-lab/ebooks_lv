# E2E: About Notice Fund Name

Goal: Verify the About page keeps `Atveseļošanās` untranslated as a proper name in all supported locales.

## Preconditions

- Start QA stack: `bash .github/qa/scripts/run_all.sh`
- Admin credentials: `admin@example.org` / `AdminTest123!`

## Steps

### English

1. Open `http://localhost:8083/stats`.
2. Switch language to **ENG**.
3. Confirm the project notice contains `Atveseļošanās Fund`.

### Latvian

1. Switch language to **LAT**.
2. Confirm the project notice contains `Atveseļošanās fonda ietvaros`.

### Russian

1. Switch language to **RUS**.
2. Confirm the project notice contains `фонда Atveseļošanās`.

## Expected

- English keeps `Atveseļošanās` untranslated.
- Latvian shows `Atveseļošanās fonda`.
- Russian keeps `Atveseļošanās` untranslated.
