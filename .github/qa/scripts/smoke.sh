#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."

echo "[smoke] Starting smoke test"

if [[ -f .github/qa/credentials.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .github/qa/credentials.env
  set +a
else
  echo "[smoke] WARNING: .github/qa/credentials.env not found; defaults will apply" >&2
fi

QA_BASE_URL="${QA_BASE_URL:-http://localhost:8083}"

# Build & run services
if command -v docker >/dev/null 2>&1; then
  echo "[smoke] Starting docker compose (dev overlay)"
  docker compose -f compose.yml -f compose.dev.yml up -d --build
else
  echo "[smoke] Docker not installed; skipping containerized run" >&2
fi

# Wait for healthz
healthz_url="${QA_BASE_URL%/}/healthz"
echo "[smoke] Waiting for $healthz_url"
for _ in {1..40}; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$healthz_url" || true)
  if [[ "$code" == "200" ]]; then
    break
  fi
  sleep 1
done

code=$(curl -s -o /dev/null -w "%{http_code}" "$healthz_url" || true)
echo "[smoke] GET $healthz_url -> $code"
if [[ "$code" != "200" ]]; then
  echo "[smoke] ERROR: healthz did not become ready" >&2
  exit 1
fi

# Optional bootstrap (safe/idempotent)
if command -v docker >/dev/null 2>&1; then
  if docker compose -f compose.yml -f compose.dev.yml ps --status running | grep -q calibre-web; then
    echo "[smoke] Bootstrapping QA users/orders (in-container)"
    docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_admin.py || true
    docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_non_admin_user.py || true
    docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_order_for_non_admin.py || true
  fi
fi

# Simple anonymous check: attempt to fetch root page (unauthenticated)
root_url="${QA_BASE_URL%/}/"
status_code=$(curl -s -o /dev/null -w "%{http_code}" "$root_url" || true)

echo "[smoke] GET $root_url -> $status_code"
if [[ "$status_code" != 2* && "$status_code" != 3* ]]; then
  echo "[smoke] ERROR: Unexpected status code" >&2
  exit 1
fi

echo "[smoke] Basic health check passed"
