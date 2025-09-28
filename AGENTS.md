
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

---
Add more rules if needed
