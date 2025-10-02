#!/usr/bin/env bash
set -euo pipefail

# Roll back calibre-web-server deployment by promoting :backup to :latest.
# Assumes registry currently has exactly two meaningful tags: latest, backup.
# Requires: doctl auth init && doctl registry login (for remote tag retag/delete).
# Optional: DRY_RUN=1 to preview actions.
# Environment overrides:
#   IMAGE_NAME (default: calibre-web-server)
#   REGISTRY   (default: registry.digitalocean.com/ebookslv-registry)
#   BACKUP_TAG (default: backup)
#   DRY_RUN    (default: 0)

IMAGE_NAME=${IMAGE_NAME:-calibre-web-server}
REGISTRY=${REGISTRY:-registry.digitalocean.com/ebookslv-registry}
BACKUP_TAG=${BACKUP_TAG:-backup}
DRY_RUN=${DRY_RUN:-0}

LATEST_REF="${REGISTRY}/${IMAGE_NAME}:latest"
BACKUP_REF="${REGISTRY}/${IMAGE_NAME}:${BACKUP_TAG}"

if ! command -v doctl >/dev/null 2>&1; then
  echo "doctl required for tag manipulation; install and authenticate first." >&2
  exit 1
fi

# Pull both images locally for safety / digest logging
echo "Pulling backup image (${BACKUP_REF})..."
docker pull "${BACKUP_REF}" >/dev/null
BACKUP_DIGEST=$(docker image inspect --format '{{.Id}}' "${BACKUP_REF}")

echo "Pulling current latest (${LATEST_REF})..." || true
docker pull "${LATEST_REF}" >/dev/null 2>&1 || true
LATEST_DIGEST=$(docker image inspect --format '{{.Id}}' "${LATEST_REF}" 2>/dev/null || echo 'missing')

echo "Current digests:" 
printf '  latest: %s\n' "${LATEST_DIGEST}"
printf '  backup: %s\n' "${BACKUP_DIGEST}"

echo "Promoting backup → latest"
if [[ "${DRY_RUN}" == "1" ]]; then
  echo "[DRY_RUN] Would delete latest tag and retag backup as latest"
else
  # Delete existing latest tag (server side) then recreate pointing to backup layers
  doctl registry repository delete-tag -f "${IMAGE_NAME}" latest || echo "(warn) failed deleting latest tag"
  docker tag "${BACKUP_REF}" "${LATEST_REF}"
  docker push "${LATEST_REF}"
fi

echo "Rollback complete. New latest digest:" $(docker image inspect --format '{{.Id}}' "${LATEST_REF}")
