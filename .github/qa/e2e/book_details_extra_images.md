# E2E: Book details extra images (mz_pictures)

## Preconditions

- Stack is up via `bash .github/qa/scripts/run_all.sh`.
- This seeds `mz_pictures` and `mz_cover_uids` for book id `3`.

## Steps

1. Open `http://localhost:8083/`.
2. Login as admin (`admin@example.org` / `AdminTest123!`).
3. Open book details for book id `3` (navigate to `/book/3` or open from catalog).
4. Verify a thumbnail strip appears below the main cover.
   - Expected: thumbnails show only the images NOT referenced by `mz_cover_uids`.
5. Click a thumbnail.
   - Expected: image opens fullscreen (same behavior as clicking the main cover).
6. Exit fullscreen (ESC).
   - Expected: main cover image is restored.

## Negative check

- Temporarily set `mz_pictures` to only include the cover uid entry.
- Refresh `/book/3`.
- Expected: thumbnail strip is not shown.
