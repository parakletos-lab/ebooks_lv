#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."

if [[ -f .github/qa/credentials.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .github/qa/credentials.env
  set +a
fi

QA_BASE_URL="${QA_BASE_URL:-http://localhost:8083}"

echo "[qa] Starting dev compose"
docker compose -f compose.yml -f compose.dev.yml up -d --build

echo "[qa] Waiting for healthz"
healthz_url="${QA_BASE_URL%/}/healthz"
for _ in {1..60}; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$healthz_url" || true)
  if [[ "$code" == "200" ]]; then
    break
  fi
  sleep 1
done
code=$(curl -s -o /dev/null -w "%{http_code}" "$healthz_url" || true)
if [[ "$code" != "200" ]]; then
  echo "[qa] ERROR: healthz not ready: $healthz_url" >&2
  exit 1
fi

echo "[qa] Bootstrapping deterministic QA users/orders (in-container)"
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_admin.py
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_non_admin_user.py
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_order_for_non_admin.py
docker compose -f compose.yml -f compose.dev.yml exec -T calibre-web python /app/.github/qa/scripts/bootstrap_price_for_sample_book.py

echo ""
echo "[qa] Ready"
echo "URL: ${QA_BASE_URL%/}/"
echo "Admin: ${QA_ADMIN_USERNAME:-admin} / ${QA_ADMIN_PASSWORD:-admin123}"
echo "User:  ${QA_USER_USERNAME:-qa_user} / ${QA_USER_PASSWORD:-qa_user123}"
echo ""
echo "Docs:"
echo "- .github/qa/e2e/roles_smoke.md"
echo "- .github/qa/e2e/non_admin_catalog_scope.md"
echo "- .github/qa/e2e/free_books_links.md"
echo "- .github/qa/e2e/mozello_theme_alignment.md"
