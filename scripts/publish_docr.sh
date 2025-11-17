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
#   ./scripts/publish_docr.sh        # bumps patch from .version
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
#   RUN_REGISTRY_GC  (default: 1) start a DigitalOcean registry GC after pruning
#   GC_INCLUDE_UNTAGGED (default: 1) GC removes untagged manifests to free space

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION_FILE="${VERSION_FILE:-${REPO_ROOT}/.version}"

IMAGE_NAME=${IMAGE_NAME:-calibre-web-server}
REGISTRY=${REGISTRY:-registry.digitalocean.com/ebookslv-registry}
PUSH_LATEST=${PUSH_LATEST:-1}
BACKUP_TAG=${BACKUP_TAG:-backup}
SKIP_BACKUP=${SKIP_BACKUP:-0}
PLATFORMS=${PLATFORMS:-linux/amd64}
PRUNE_OTHERS=${PRUNE_OTHERS:-1}
DRY_RUN=${DRY_RUN:-0}
RUN_REGISTRY_GC=${RUN_REGISTRY_GC:-1}
GC_INCLUDE_UNTAGGED=${GC_INCLUDE_UNTAGGED:-1}
REGISTRY_NAME_ONLY=${REGISTRY_NAME_ONLY:-${REGISTRY##*/}}

start_registry_gc(){
  local registry_name="$1"
  local include_untagged="$2"
  local dry_run="$3"
  if [[ -z "$registry_name" ]]; then
    echo "Cannot start registry garbage collection: registry name missing" >&2
    return 1
  fi
  local args=("$registry_name")
  local include_flag="--force"
  if [[ "$include_untagged" == "1" ]]; then
    args+=("--include-untagged-manifests")
  fi
  if [[ "$dry_run" == "1" ]]; then
    echo "[DRY_RUN] Would run: doctl registry garbage-collection start ${args[*]} ${include_flag}"
    return 0
  fi
  echo "Starting registry garbage collection for ${registry_name} (include_untagged=${include_untagged})"
  if ! doctl registry garbage-collection start "${args[@]}" "${include_flag}"; then
    echo "Primary GC invocation failed; retrying with legacy --disable-confirmation flag" >&2
    if ! doctl registry garbage-collection start "${args[@]}" "--disable-confirmation"; then
      echo "Warning: failed to start registry garbage collection" >&2
      return 1
    fi
  fi
}

SHOULD_UPDATE_VERSION_FILE=0

parse_version(){
  local raw="$1"
  local __prefix_var="$2"
  local __major_var="$3"
  local __minor_var="$4"
  local __patch_var="$5"
  local version="$raw"
  local prefix=""
  if [[ "$version" =~ ^[vV] ]]; then
    prefix="${version:0:1}"
    version="${version:1}"
  fi
  IFS='.' read -r major minor patch remainder <<< "$version"
  unset IFS
  major=${major:-0}
  minor=${minor:-0}
  patch=${patch:-0}
  if [[ -n "$remainder" ]]; then
    return 1
  fi
  if ! [[ "$major" =~ ^[0-9]+$ && "$minor" =~ ^[0-9]+$ && "$patch" =~ ^[0-9]+$ ]]; then
    return 1
  fi
  printf -v "$__prefix_var" '%s' "$prefix"
  printf -v "$__major_var" '%s' "$major"
  printf -v "$__minor_var" '%s' "$minor"
  printf -v "$__patch_var" '%s' "$patch"
  return 0
}

next_patch_version(){
  local raw="$1"
  local prefix major minor patch
  if ! parse_version "$raw" prefix major minor patch; then
    return 1
  fi
  patch=$((patch + 1))
  printf '%s%s.%s.%s\n' "$prefix" "$major" "$minor" "$patch"
}

read_version_file(){
  local file="$1"
  if [[ -f "$file" ]]; then
    tr -d '[:space:]' < "$file"
  fi
}

persist_version_file(){
  local file="$1"
  local value="$2"
  if ! printf '%s\n' "$value" > "$file"; then
    echo "Warning: failed to update version file $file" >&2
    return 1
  fi
  echo "Updated $file to $value"
}

trackable_version(){
  local raw="$1"
  local _p _maj _min _patch
  if parse_version "$raw" _p _maj _min _patch; then
    unset _p _maj _min _patch
    return 0
  fi
  unset _p _maj _min _patch
  return 1
}

# Determine tag argument or environment provided VERSION
TAG_ARG=${1:-}
REQUESTED_VERSION=${VERSION:-${TAG_ARG:-}}
if [[ -z "$REQUESTED_VERSION" ]]; then
  current_version=$(read_version_file "$VERSION_FILE")
  if [[ -n "$current_version" ]]; then
    if ! VERSION=$(next_patch_version "$current_version"); then
      echo "Unable to derive next version from $VERSION_FILE (found: $current_version)" >&2
      exit 1
    fi
    echo "Auto-generated version $VERSION from $VERSION_FILE"
  else
    VERSION="0.0.1"
    echo "Auto-generated version $VERSION (starting new sequence)"
  fi
  SHOULD_UPDATE_VERSION_FILE=1
else
  VERSION="$REQUESTED_VERSION"
  if trackable_version "$VERSION"; then
    SHOULD_UPDATE_VERSION_FILE=1
  fi
fi

if [[ -z "${VERSION}" ]]; then
  echo "No version/tag provided. Provide an argument, set VERSION env var, or ensure $VERSION_FILE is valid." >&2
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

if [[ "${RUN_REGISTRY_GC}" == "1" ]]; then
  if command -v doctl >/dev/null 2>&1; then
    start_registry_gc "${REGISTRY_NAME_ONLY}" "${GC_INCLUDE_UNTAGGED}" "${DRY_RUN}" || true
  else
    echo "doctl not found; skipping registry garbage collection" >&2
  fi
else
  echo "Skipping registry garbage collection (RUN_REGISTRY_GC=${RUN_REGISTRY_GC})"
fi

if [[ "${SHOULD_UPDATE_VERSION_FILE}" == "1" ]]; then
  persist_version_file "$VERSION_FILE" "$VERSION" || true
fi

echo "Done. Registry should now contain at most: latest and ${BACKUP_TAG}."
