# QA Assets

This directory houses QA / test automation artifacts for the custom Copilot Chat "QA Autopilot" mode.

Contents:
- `credentials.template.env` – Placeholder for local test credentials (never commit real secrets). Copy to `credentials.env` locally.
- `scripts/` – Re-runnable smoke and E2E helper scripts.
- (future) `screens/` – Optional textual HTML snapshots or base64 images for analysis (avoid storing large binaries in git).

Guidelines:
1. Keep scripts idempotent; re-running should not require manual cleanup.
2. Never place production credentials here. Use placeholders only.
3. Temporary debug code must be removed before merging changes.
4. Prefer plugin-scoped changes (see `AGENTS.md`) over editing `calibre-web/` core.
5. Keep added comments minimal—just enough for maintainability.

Update this README if new tooling or environment variables are introduced.
