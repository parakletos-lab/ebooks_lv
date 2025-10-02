#!/usr/bin/env bash
set -euo pipefail

# Publish image to DigitalOcean Container Registry with backup + aggressive pruning.
#
# Features:
#   1. Optionally pulls current :latest and retags it as :backup before pushing new image.
#   2. Builds image locally (single or multi-arch) using a provided version tag (local only).
#   3. Pushes ONLY :latest (and :backup) remote so registry holds at most two tags.
#   4. Prunes all other remote tags (requires doctl) unless disabled.
#
# Prerequisites:
#   doctl auth init  (and already logged in)
#   doctl registry login
#   docker buildx installed (optional for multi-arch)
#
# Usage:
#   ./scripts/publish_docr.sh <version_tag>
# Examples:
#   ./scripts/publish_docr.sh v0.1.0
#   ./scripts/publish_docr.sh $(git rev-parse --short HEAD)
#   VERSION=$(date +%Y%m%d%H%M) ./scripts/publish_docr.sh
#
# Environment overrides:
#   IMAGE_NAME       (default: calibre-web-server)
#   REGISTRY         (default: registry.digitalocean.com/ebookslv-registry)
#   PUSH_LATEST      (default: 1) set 0 to skip pushing :latest (rare)
#   BACKUP_TAG       (default: backup) previous latest is tagged to this before update
#   SKIP_BACKUP      (default: 0) set 1 to skip backup tagging
#   PLATFORMS        (default: linux/amd64) override for buildx multi-arch (comma list)
#   PRUNE_OTHERS     (default: 1) delete all remote tags except latest & backup
#   DRY_RUN          (default: 0) if 1, show actions without mutating registry

IMAGE_NAME=${IMAGE_NAME:-calibre-web-server}
REGISTRY=${REGISTRY:-registry.digitalocean.com/ebookslv-registry}
PUSH_LATEST=${PUSH_LATEST:-1}
BACKUP_TAG=${BACKUP_TAG:-backup}
SKIP_BACKUP=${SKIP_BACKUP:-0}
PLATFORMS=${PLATFORMS:-linux/amd64}
PRUNE_OTHERS=${PRUNE_OTHERS:-1}
DRY_RUN=${DRY_RUN:-0}

# Determine tag argument or environment provided VERSION
TAG_ARG=${1:-}
VERSION=${VERSION:-${TAG_ARG:-}}
if [[ -z "${VERSION}" ]]; then
  echo "No version/tag provided. Provide an argument or set VERSION env var." >&2
  exit 1
fi

FULL_TAG="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
LATEST_TAG="${REGISTRY}/${IMAGE_NAME}:latest"
BACKUP_FULL_TAG="${REGISTRY}/${IMAGE_NAME}:${BACKUP_TAG}"

if [[ "${VERSION}" == "latest" || "${VERSION}" == "${BACKUP_TAG}" ]]; then
  echo "Refusing to build with reserved tag name: ${VERSION}" >&2
  exit 2
fi

if [[ "${SKIP_BACKUP}" == "0" && "${PUSH_LATEST}" == "1" ]]; then
  echo "Attempting to pull existing latest for backup..."
  if docker pull "${LATEST_TAG}" >/dev/null 2>&1; then
    echo "Tagging previous latest as ${BACKUP_FULL_TAG}"
    docker tag "${LATEST_TAG}" "${BACKUP_FULL_TAG}" || {
      echo "Failed to tag backup" >&2; exit 3; }
    echo "Pushing backup tag ${BACKUP_FULL_TAG}"
    docker push "${BACKUP_FULL_TAG}" || {
      echo "Failed to push backup tag" >&2; exit 4; }
  else
    echo "No existing latest image found (skip backup)."
  fi
else
  echo "Skipping backup of previous latest (SKIP_BACKUP=${SKIP_BACKUP}, PUSH_LATEST=${PUSH_LATEST})"
fi

echo "Building ${FULL_TAG} (platforms: ${PLATFORMS})"
if docker buildx version >/dev/null 2>&1; then
  docker buildx build --platform "${PLATFORMS}" -t "${FULL_TAG}" . --load
else
  if [[ "${PLATFORMS}" != "linux/amd64" ]]; then
    echo "WARNING: buildx not available; ignoring multi-platform request (${PLATFORMS})" >&2
  fi
  docker build -t "${FULL_TAG}" .
fi

if [[ "${PUSH_LATEST}" == "1" ]]; then
  echo "Tagging local build as latest"
  docker tag "${FULL_TAG}" "${LATEST_TAG}" || { echo "Failed to tag latest" >&2; exit 6; }
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "[DRY_RUN] Would push ${FULL_TAG}"; [[ "${PUSH_LATEST}" == "1" ]] && echo "[DRY_RUN] Would push ${LATEST_TAG}" || true
else
  echo "Pushing build layers via version tag (will prune remote tag after)"
  docker push "${FULL_TAG}" || { echo "Failed to push ${FULL_TAG}" >&2; exit 5; }
  if [[ "${PUSH_LATEST}" == "1" ]]; then
    echo "Pushing latest"
    docker push "${LATEST_TAG}" || { echo "Failed to push latest" >&2; exit 7; }
  fi
fi

# Prune all other remote tags so only latest & backup remain.
if [[ "${PRUNE_OTHERS}" == "1" ]]; then
  if command -v doctl >/dev/null 2>&1; then
    echo "Pruning remote tags (keeping: latest, ${BACKUP_TAG})"
    TAGS=""
    if command -v jq >/dev/null 2>&1; then
      # Prefer JSON for reliable parsing
      TAGS=$(doctl registry repository list-tags "${IMAGE_NAME}" --output json 2>/dev/null | jq -r '.[].tag' || true)
    fi
    if [[ -z "${TAGS}" ]]; then
      # Fallback: plain table parse (take first column, skip header)
      TAGS=$(doctl registry repository list-tags "${IMAGE_NAME}" 2>/dev/null | awk 'NR>1 {print $1}' || true)
    fi
    # De-duplicate
    UNIQUE_TAGS=$(echo "${TAGS}" | awk 'NF {print}' | sort -u)
    while IFS= read -r tag; do
      [[ -z "${tag}" ]] && continue
      [[ "${tag}" == "latest" || "${tag}" == "${BACKUP_TAG}" ]] && continue
      if [[ "${DRY_RUN}" == "1" ]]; then
        echo "[DRY_RUN] Would delete remote tag: ${tag}"
      else
        echo "Deleting remote tag: ${tag}"
        doctl registry repository delete-tag -f "${IMAGE_NAME}" "${tag}" || echo "Warning: failed to delete ${tag}" >&2
      fi
    done <<< "${UNIQUE_TAGS}"
  else
    echo "doctl not found; skipping prune. Install doctl to enable PRUNE_OTHERS." >&2
  fi
else
  echo "Skipping prune (PRUNE_OTHERS=${PRUNE_OTHERS})"
fi

# Remove the remote version tag we just pushed if it's neither latest nor backup (enforces only two remote tags)
if [[ "${DRY_RUN}" == "0" && "${VERSION}" != "latest" && "${VERSION}" != "${BACKUP_TAG}" && "${PRUNE_OTHERS}" == "1" ]]; then
  if command -v doctl >/dev/null 2>&1; then
    echo "Removing intermediate version tag ${VERSION} (keeping only latest & backup)"
    doctl registry repository delete-tag -f "${IMAGE_NAME}" "${VERSION}" || echo "Warning: failed to delete version tag ${VERSION}" >&2
  fi
fi

echo "Done. Registry should now contain at most: latest and ${BACKUP_TAG}."
