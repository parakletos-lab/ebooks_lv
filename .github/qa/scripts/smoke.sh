#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."

echo "[smoke] Starting smoke test"

if [[ -f .github/qa/credentials.env ]]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' .github/qa/credentials.env | xargs -I{} echo {})
else
  echo "[smoke] WARNING: credentials.env not found; using template placeholders" >&2
fi

# Build & run services
if command -v docker >/dev/null 2>&1; then
  echo "[smoke] Building docker images (compose)"
  docker compose -f compose.yaml up -d --build
else
  echo "[smoke] Docker not installed; skipping containerized run" >&2
fi

# Simple health check: attempt to fetch root page (unauthenticated)
HEALTH_URL="http://localhost:8083" # adjust if compose.yaml exposes different port
status_code=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" || true)

echo "[smoke] GET $HEALTH_URL -> $status_code"
if [[ "$status_code" != 2* && "$status_code" != 3* ]]; then
  echo "[smoke] ERROR: Unexpected status code" >&2
  exit 1
fi

echo "[smoke] Basic health check passed"
