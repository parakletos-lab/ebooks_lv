# QA Assets

This directory houses QA / test automation artifacts for the custom Copilot Chat "QA Autopilot" mode.

Contents:
- `credentials.env` – Placeholder for local test credentials
- `scripts/` – Re-runnable smoke and E2E helper scripts.
- `screens/` – Optional textual HTML snapshots or base64 images for analysis (avoid storing large binaries in git).
- `e2e/` - End to end tests

Guidelines:
1. Keep scripts idempotent; re-running should not require manual cleanup.
2. Temporary debug code must be removed before merging changes.

Update this README if new tooling or environment variables are introduced.
