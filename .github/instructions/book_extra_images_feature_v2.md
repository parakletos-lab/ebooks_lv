# Feature Design (Alternative V2): Description-Embedded Images Extraction & Link Rewriting

Status: PLANNED / EXPERIMENTAL (do NOT implement without explicit approval). This variant leverages images embedded or referenced in the Calibre description (comments HTML) instead of a dedicated `extra_images/` folder. Keep this doc authoritative for this approach.

## 1. Goal
Allow editors to place multiple images directly in the Calibre book description. During export to Mozello:
1. Parse description HTML.
2. Extract image references (either relative filenames or base64 data URIs).
3. Produce Mozello product pictures (optional) OR rewrite relative references to absolute, publicly accessible URLs served by our app.
4. Send a cleaned (image-stripped or rewritten) description to Mozello.

## 2. Inputs & Image Forms
- Relative file references: `<img src="map1.jpg" alt="Map">` (Calibre copied `map1.jpg` into the book folder).
- Data URIs: `<img src="data:image/png;base64,iVBOR..." alt="Graph">` (inline base64). 
- Optional absolute external URLs (ignored or preserved based on policy).

## 3. Output Modes (Choose One or Hybrid)
| Mode | Description HTML Sent to Mozello | Product Pictures | Pros | Cons |
|------|----------------------------------|------------------|------|------|
| A: Self-host links | Relative `<img>` rewritten to absolute our-domain URLs | None | Fast, minimal Mozello API usage | Availability coupling, no CDN, broken if paths change |
| B: Mozello pictures, strip | All `<img>` removed (or replaced with placeholders) | Yes (all images uploaded) | Clean description, CDN delivery | Two-phase parse + upload; loses narrative placement |
| C: Mozello pictures, inline Mozello URLs | `<img>` tags rewritten to Mozello-hosted URLs | Yes | Preserves placement & gallery | Requires second update or ordering coordination |
| D: Hybrid (cover kept inline, others gallery) | One hero `<img>` (local or Mozello URL), rest stripped | Optional | Balanced layout | Extra branching logic |

Default recommendation if this approach adopted: Mode C (retain context + Mozello hosting), falling back to Mode B if update ordering complexity too high initially.

## 4. Why Consider / Why Avoid
Pros:
- Zero new UI; editors use existing rich text environment.
- Implicit ordering from narrative.
- No separate manifest maintenance.

Cons:
- Large HTML bloat (especially with base64 embeds) inflates `metadata.db` & `metadata.opf`.
- Difficult dedupe; repeated images appear multiple times unless hashed.
- Risk of leaving giant data URIs in Mozello description if extraction bug occurs.
- Harder to evolve (thumbnails, metadata, alt text normalization) vs a structured folder.

If complexity grows, prefer the folder+manifest design (see `book_extra_images_feature.md`).

## 5. Extraction & Rewriting Algorithm (Export Time)
1. Fetch description HTML (`comments.text`).
2. Parse with an HTML parser (NO regex) – e.g. `html5lib` or `BeautifulSoup` (adds dependency) or Python `html.parser` (more brittle).
3. Iterate `<img>` tags:
   - Classify `src`:
     - `data:` → decode base64; compute SHA256.
     - Relative (no scheme, doesn’t start `/`) → treat as file path candidate.
     - Absolute HTTP(S) → preserve or (optionally) reject per policy.
4. For relative files:
   - Validate filename against whitelist regex `^[A-Za-z0-9._-]{1,80}$`.
   - Build absolute served URL: `PUBLIC_BASE/ebookslv/book/<book_id>/image/<filename>` (requires public serve endpoint).
5. For base64 images:
   - If Mode A: persist to temp file in memory (NOT served) – optionally skip (cannot link without writing file).
   - If Mozello product picture upload mode (B/C): keep bytes for upload.
6. Deduplicate by SHA256: maintain `hash → image_record` map. Reuse previously uploaded Mozello picture or re-link.
7. Apply transformation per chosen mode (strip / rewrite / replace with Mozello URLs / partial).
8. Truncate description after transformation if above size threshold (e.g. 20k chars) – log warning.
9. Upload (if required) each deduped image to Mozello respecting throttle.
10. If Mode C (inline Mozello URLs): after uploads, perform second pass rewriting placeholder tokens to final Mozello URLs and send final PUT update.

## 6. Public Serving Endpoint (For Mode A / Hybrid Inline Local)
- Route: `GET /ebookslv/book/<int:book_id>/image/<filename>`
- Validation: ensure resolved path stays inside book directory.
- Headers: `Cache-Control: public, max-age=86400`; `ETag` = SHA256.
- Optional: query param `?w=...` for future resizing (not MVP).

## 7. Mozello Upload Mapping (Modes B/C)
- After each successful `add_product_picture`, store remote UID + original hash in a local cache (in-memory or a JSON sidecar, e.g., `<bookdir>/extracted_images_cache.json`).
- Schema suggestion:
  ```json
  {
    "pictures": [
      {"hash": "sha256:abc...", "filename": "map1.jpg", "remote_uid": "uid-123", "source": "relative|data_uri", "original_src": "map1.jpg"}
    ]
  }
  ```
- Use this cache to prevent re-uploading identical images on subsequent exports.

## 8. Placeholder Strategy (Mode C two-phase)
During first pass, replace each `<img>` with: `<span data-img-hash="sha256:..." class="mz-img-ph"></span>`.
After remote uploads, second pass replaces each placeholder with Mozello-hosted `<img src="<mozello_url>" alt="...">`.

## 9. Alt Text & Accessibility
- Preserve `alt` attribute; if missing, generate from filename (strip extension, replace dashes with spaces).
- Limit alt length (e.g. 120 chars). Truncate gracefully.

## 10. Error Handling
| Scenario | Action |
|----------|--------|
| Missing relative file | Log warning, remove `<img>` node |
| Invalid filename pattern | Skip + warn |
| Base64 decode failure | Skip + warn |
| Oversized image (>5MB) | Skip or downscale (future) |
| Mozello upload fails | Keep placeholder note `[Image upload failed]` (log) |
| Second pass mismatch (hash not found) | Remove placeholder, warn |

## 11. Security Considerations
- Strip potentially dangerous attributes: `on*`, `style` containing `expression`, `javascript:` URLs.
- Remove `<script>` & `<iframe>` outright.
- Enforce MIME whitelist: `image/jpeg`, `image/png`, `image/webp`, `image/gif` (decide on GIF acceptance).
- Ensure no path traversal in relative images.

## 12. Performance & Limits
- Avoid loading massive data URIs fully if they exceed a configured limit (e.g. >6MB) – short-circuit.
- Throttle Mozello API already enforced (1 req/sec). For many images per book, this slows export; consider grouping or future batch endpoint (if Mozello exposes one later).

## 13. Configurable Constants (Proposed)
| Constant | Default | Purpose |
|----------|---------|---------|
| MAX_INLINE_IMG_BYTES | 6_000_000 | Reject huge data URIs |
| MAX_DESCRIPTION_EXPORT_CHARS | 20_000 | Size guard for Mozello payload |
| EXPORT_IMG_MODE | "mozello_inline" | One of: `local_links`, `mozello_gallery`, `mozello_inline`, `hybrid` |
| IMG_HASH_ALGO | sha256 | Hash digest for dedupe |

Expose via `app.config` accessors if implemented (update `AGENTS.md` when adding).

## 14. Comparison vs Folder Manifest Approach
| Criterion | V2 (Description Parsing) | V1 (extra_images folder) |
|-----------|--------------------------|--------------------------|
| Editor UX | Single WYSIWYG surface | Separate step for images |
| Complexity | High (parsing, rewriting) | Lower (filesystem ops) |
| Dedupe Ease | Must hash extracted content | Natural by filename/hash at save |
| Risk of Data Bloat | Higher (base64 in HTML) | Lower |
| Future Features (ordering, captions) | Harder (HTML dependent) | Easier (manifest fields) |

## 15. Migration Path (If Switching to Folder Later)
1. Run export parser one time; for each image create file in `extra_images/` with hashed name.
2. Clean description (remove all `<img>` or convert to remote Mozello URLs).
3. Deprecate parser on subsequent exports in favor of structured manifest.

## 16. Acceptance Criteria (If Implemented)
- Export detects and processes all <img> tags (data URIs + relative) without raising unhandled exceptions.
- Duplicate images (identical bytes) upload only once per export.
- Description sent to Mozello contains no `data:` URLs.
- Configurable mode switch controls final behavior (gallery vs inline vs local links).
- Logs summarize: images_found, uploaded, skipped (with reasons), transformed_description_chars.

## 17. Open Questions
- Does Mozello sanitize remote `<img>` tags linking to external domains? (Confirm before relying on Mode A only.)
- Should we downscale very large images automatically (Pillow)?
- Retain ordering: if uploading to Mozello gallery, does order of upload define display sequence? (Empirical test needed.)
- Cache eviction: how to handle deleting images from description—should we prune previous remote pictures?

## 18. Decision Guidance
Adopt this only if editorial simplicity (drop images directly into description) outweighs parsing complexity. Otherwise proceed with V1.

## 19. Implementation Steps (If Greenlit)
1. Add config flags & constants.
2. Implement `description_images.extract(html, book_id)` -> structured list + transformed intermediate HTML.
3. Implement dedupe hash & remote upload loop (respect throttle).
4. Implement second-pass rewriting (Mode C) or removal (Mode B).
5. Add logging & metrics counters.
6. Extend export endpoint to call new extractor before `upsert_product_basic`.
7. (Optional) Add dry-run admin endpoint to preview extraction diff.

---
Keep this file updated if any assumptions change. Do **not** partially implement without marking which modes are supported to avoid ambiguous export behavior.
