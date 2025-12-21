# Mozello non-destructive re-sync (cover-only)

Goal: verify that re-syncing a book to Mozello updates supported fields without deleting extra Mozello data, and that only previously uploaded Calibre cover picture(s) are replaced.

This check uses the local Mozello mock server via `.github/qa/compose.mozello-mock.yml` (started by `bash .github/qa/scripts/run_all.sh`).

## Setup
1. Start QA stack:
   - `bash .github/qa/scripts/run_all.sh`
2. Log in as admin:
   - URL: `http://localhost:8083/login`
   - `admin / AdminTest123!`
3. Configure Mozello API key (any non-empty value):
   - Go to `http://localhost:8083/admin/mozello/`
   - Set **Mozello API Key** to `test-key`
   - Click **Save Settings**

## Steps
1. Go to `http://localhost:8083/admin/ebookslv/books/`.
2. Trigger a sync for an arbitrary book row (prefer a low id like 1):
   - Click the per-book **Sync to Mozello** button.
3. Add an extra (non-Calibre) image directly into the Mozello mock:
   - `curl -s -X POST http://localhost:9090/v1/store/product/book-1/picture/ \
        -H 'Authorization: ApiKey test-key' -H 'Content-Type: application/json' \
        -d '{"picture": {"filename": "extra.jpg", "data": "Zm9v"}}' | cat`
4. Record picture list:
   - `curl -s http://localhost:9090/v1/store/product/book-1/pictures/ -H 'Authorization: ApiKey test-key' | cat`
5. Re-sync the same book again from `http://localhost:8083/admin/ebookslv/books/`.
6. Fetch picture list again:
   - `curl -s http://localhost:9090/v1/store/product/book-1/pictures/ -H 'Authorization: ApiKey test-key' | cat`

## Expected
- The list after step 6 still contains the `extra.jpg` picture uid (extra Mozello data preserved).
- The Calibre cover uid changes between step 4 and step 6 (cover is recreated).
- No other pictures are removed.
