
## Agent Quick Rules

1. Never touch core without approval.
2. Use service layer (no raw SQL). 
3. Invalidate cache after every mutation.
4. Use config accessors (not raw os.environ in logic).
5. Don’t fabricate IDs; allow‑list is authoritative.
6. Only widen (fail open) under documented skip conditions.
7. Keep this file updated if new env vars or services are added.
8. Before tests rebuild docker container.
9. For tests prefer chrome-devtools MCP (DOM snapshot + key selectors + network).

10. Use `app.config.*` accessors for environment derived settings (avoid raw os.getenv in business logic).
11. Navigation link injection lives in `app.routes.overrides.nav_injection`.
12. Logging must go through `app.utils.logging.get_logger`.
13. Repositories/services must not import from any retired namespace.
14. If adding a new env var, document it here and implement accessor in `app.config`.

15. After adding or editing any admin UI page (templates/routes): rebuild container (`docker compose up -d --build calibre-web-server`) and verify page source has its hidden CSRF `<input>` before testing API actions (prevents stale template/CSRF misses).

16. Field design additions:
	- `mz_price` custom float column is auto-created at startup if missing by `entrypoint/seed_library.py` (idempotent).
	- `mz_handle` stored as Calibre identifier `type='mz'` (no schema env var required).

17. For Mozello Store API (products/orders/webhooks) implementation details, consult `.github/instructions/mozello_store_api.md` (single source; do not duplicate large doc excerpts in code or comments).

18. Throttle Mozello Store API calls: maximum 1 request per second (enforced in mozello_service). Serialize all product operations.

19. Extra book images:
	- Upload limit defaults: MAX_IMAGE_BYTES=3MB, MAX_IMAGES_PER_BOOK=10 (manifest enforced), MAX_TOTAL_BYTES_PER_BOOK=15MB.
	- Manifest stored at extra_images_manifest.json alongside files; mozello sync flags live there.
	- Mozello picture uploads respect 1 req/s throttle; pending_remote flag remains until successful API response.

---
Add more rules if needed
