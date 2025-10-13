# Feature Design: Extra Book Images (Local Gallery + Mozello Sync)

Status: PLANNED (not implemented). Keep this document authoritative for this feature; update upon implementation changes.

## 1. Goal
Enable multiple supplemental images per book beyond the single Calibre cover, stored alongside the book in the library filesystem, visible on public book detail pages, and (optionally) uploaded to Mozello as product pictures.

## 2. Non-Goals (Initial MVP)
- No background job queue or async workers (synchronous best-effort uploads only).
- No remote -> local sync (only local → Mozello push).
- No variant-specific images (variants not in scope yet).
- No complex ordering UI (natural chronological order only) – ordering may be a later enhancement.

## 3. Storage Model
- Directory: `<library_root>/<book.path>/extra_images/`
- Filenames: `img-<epoch_ms>-<rand8>.<ext>` to avoid collisions.
- Allowed extensions: `jpg`, `jpeg`, `png`, `webp` (reject others).
- Size limit: 3 MB per file (configurable constant in service).
- Optional Manifest: `extra_images_manifest.json` in same folder:
  ```json
  {
    "files": [
      {"name": "img-...jpg", "sha256": "...", "uploaded_remote": true, "remote_uid": "uid-..."}
    ]
  }
  ```
  - Manifest enables dedupe, remote reconciliation, and status flags.

## 4. Services
Create `app/services/book_images.py` with:
- `get_book_path(book_id) -> str | None`
- `list_images(book_id) -> { files: [ { name, size, mtime, uploaded_remote?, remote_uid? } ] }`
- `save_image(book_id, file_storage) -> (ok, info|error)` (handles validation, naming, hashing, manifest update)
- `delete_image(book_id, filename, delete_remote: bool=False)`
- `encode_image_base64(book_id, filename) -> (ok, b64)` (size re-check)
- `mark_remote_uploaded(book_id, filename, remote_uid)` (updates manifest)
- Internals: path traversal guard, limit max images (default 10).

## 5. Flask Endpoints (Admin JSON)
Under existing blueprint `ebookslv_admin` (do NOT modify Calibre-Web core):
1. `POST /admin/ebookslv/books/<int:book_id>/images/upload`
   - multipart form-data field: `file`
   - Returns `{ ok: true, image: {...}, mozello: { uploaded: bool } }` or `{ error: code }`
2. `GET /admin/ebookslv/books/<int:book_id>/images/list`
   - Returns `{ images: [...], count, limit }`
3. `DELETE /admin/ebookslv/books/<int:book_id>/images/<filename>`
   - Optional query `remote=1` to also attempt Mozello DELETE if `remote_uid` exists.
4. (Later) `POST /admin/ebookslv/books/<int:book_id>/images/sync_remote` to retry pending uploads.

CSRF: Exempt similarly to existing Books API JSON endpoints via `_maybe_exempt` helper.

## 6. Public Read Endpoints
Separate lightweight blueprint or reuse existing one with neutral prefix:
- `GET /ebookslv/book/<int:book_id>/images.json` → `{ images: [ { url, name } ] }`
- `GET /ebookslv/book/<int:book_id>/image/<filename>` → streams file.
  - Optional `?thumb=1&max=200` (future) to return cached resized thumbnail.

Access Control: Initial assumption public; if later restricted, add allow‑list check before serving.

## 7. Mozello Integration
- On successful local save, if book already exported (has `mz_handle`), immediately base64 encode and call `mozello_service.add_product_picture(handle, b64, filename)`.
- On success: record `uploaded_remote=true` + `remote_uid` (if returned) in manifest.
- If `mz_handle` absent, mark `pending_remote=true`; after product export (single/bulk), add a pass to upload pending images.
- Remote operations must respect existing throttle (1 req/sec rule #18). Each image upload is a separate API call.

## 8. Client-Side Admin UI
Enhance `/admin/ebookslv/books/` table:
- Add an "Images" button for rows with a `book_id`.
- Modal (injected via JS) includes:
  - Current image grid (thumbnails -> uses public image URL; can add `loading="lazy"`).
  - Upload form (drag-drop + click to select). On submit → POST upload endpoint.
  - Delete icon per image (sends DELETE then refresh list).
  - Remote status badge: local-only / uploaded / pending / failed.

Add minimal JS module `ebookslv_images.js` loaded on the Books page (extend existing template). Keep logic isolated.

## 9. Public Book Page Gallery Injection
- Reuse existing layout or nav injection: small inline script checks URL pattern `/book/<id>`.
- Fetch `/ebookslv/book/<id>/images.json`.
- If images exist: create container below existing cover with a flex/grid gallery.
- Optional lightbox (simple overlay, no dependency) – future.

## 10. Validation & Limits
- Reject: oversize, unsupported type, > max images, empty file.
- Enforce path safety: after joining, ensure `abs_path.startswith(book_dir)`.
- Hash content (SHA256). If identical hash already stored for the book, skip writing new file and return existing record (idempotency).

## 11. Error Codes (JSON)
| Code | Meaning |
|------|---------|
| `book_not_found` | Calibre book id path lookup failed |
| `file_missing` | No file part in upload |
| `unsupported_type` | Extension not allowed |
| `file_too_large` | Exceeds per-file max bytes |
| `limit_reached` | Image count limit hit |
| `io_error` | Filesystem write/delete error |
| `upload_failed` | Mozello picture upload failed (non-fatal for local save) |

## 12. Logging
- Logger name: `book_images`.
- Info on upload success with book_id, filename, size, remote sync result.
- Warning on rejections (include reason).
- Debug for manifest reads/writes if needed.

## 13. Future Enhancements (Not in MVP)
- Thumbnail generation & caching.
- Remote reconciliation (`GET /pictures/` vs manifest diff) and orphan cleanup.
- Image ordering + drag & drop reorder API.
- Background job queue / retry for failed remote uploads.
- WebP on-the-fly conversion to reduce size.
- CDN caching headers for public images.

## 14. Security Considerations
- Strict filename sanitization.
- Limit total disk usage (optional: compute aggregate size across images; refuse if > 15MB/book).
- Avoid exposing internal paths in responses.
- Potential rate limiting (simple in-memory counter) to deter abuse if public upload ever considered (currently admin only).

## 15. Implementation Checklist (MVP)
1. Service module & helpers.
2. Admin endpoints (upload, list, delete) + CSRF exemptions.
3. Public endpoints (JSON list + image stream).
4. JS modal integration on Books admin page.
5. Gallery injection script for public detail page.
6. Mozello upload call integrated with throttle.
7. Manifest persistence & status flags.
8. Documentation update (this file) and add brief note in `AGENTS.md` if new config or rules introduced.

## 16. Acceptance Criteria Summary
- Upload of valid file returns 200 JSON with image entry and remote upload attempt status.
- Listing shows all stored images with correct counts.
- Deleting removes file and manifest entry.
- Public `/ebookslv/book/<id>/images.json` returns only names/urls (no internal metadata) and loads on a valid book (0 images → empty array).
- Gallery appears on `/book/<id>` only when extra images exist.
- Mozello picture upload attempted immediately when handle exists (observed via logs).

---
Update this document as soon as implementation diverges. Do not copy large public doc excerpts here; keep integration specifics concise.
