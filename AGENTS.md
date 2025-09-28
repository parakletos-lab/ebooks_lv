
## Agent Quick Rules

1. Never touch core without approval.
2. Use service layer (no raw SQL). 
3. Invalidate cache after every mutation.
4. Use config accessors (not raw os.environ in logic).
5. Don’t fabricate IDs; allow‑list is authoritative.
6. Only widen (fail open) under documented skip conditions.
7. Keep this file updated if new env vars or services are added.

### QA Tests
- Rebuild docker container before testing if needed
- Prefer Chrome DevTools MCP (DOM snapshot + key selectors + network).

---
Add more rules if needed
