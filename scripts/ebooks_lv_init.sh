#!/usr/bin/env bash
# One-time (idempotent) initialization script for ebooks_lv.
# Safe to re-run; it only creates/fixes directories, copies initial metadata.db
# if a library migration (Option A) is detected, and prepares environment file.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/ebooks_lv}"
ENV_FILE="${APP_DIR}/.env"
COMPOSE_FILES="-f compose.yml -f compose.droplet.yml"
CALIBRE_HOST_CONFIG="/opt/calibre/config"
CALIBRE_HOST_LIBRARY="/opt/calibre/library"
LEGACY_LIB_IN_REPO="${REPO_ROOT}/library"
APPUSER_UID=1000
APPUSER_GID=1000

log(){ echo "[init] $*"; }
err(){ echo "[init][error] $*" >&2; }

need_bins(){
  local missing=0
  for b in docker git; do
    command -v $b >/dev/null 2>&1 || { err "Missing required binary: $b"; missing=1; }
  done
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  else
    err "Missing docker compose plugin or docker-compose binary"; missing=1
  fi
  [ $missing -eq 0 ] || { err "Install missing dependencies then re-run."; exit 1; }
  log "Using compose command: $COMPOSE_CMD"
}

ensure_env(){
  if [ ! -f "$ENV_FILE" ]; then
    log "Creating env file $ENV_FILE"
    mkdir -p "${APP_DIR}" && touch "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi
}

preflight_dirs(){
  log "Ensuring calibre config & library directories exist"
  for d in "$CALIBRE_HOST_CONFIG" "$CALIBRE_HOST_LIBRARY"; do
    if [ -e "$d" ] && [ ! -d "$d" ]; then
      err "Path $d exists but is not a directory"; exit 12
    fi
    [ -d "$d" ] || mkdir -p "$d"
  done
  if [ "$(id -u)" = "0" ]; then
    for d in "$CALIBRE_HOST_CONFIG" "$CALIBRE_HOST_LIBRARY"; do
      local uid gid
      uid=$(stat -c '%u' "$d") || true
      gid=$(stat -c '%g' "$d") || true
      if [ "$uid" != "$APPUSER_UID" ] || [ "$gid" != "$APPUSER_GID" ]; then
        log "Chown $d -> $APPUSER_UID:$APPUSER_GID"
        chown -R $APPUSER_UID:$APPUSER_GID "$d"
      fi
      chmod 755 "$d" || true
    done
  else
    log "Not root; skipping chown (ensure perms manually if needed)"
  fi
  for d in "$CALIBRE_HOST_CONFIG" "$CALIBRE_HOST_LIBRARY"; do
    if ! touch "$d/.writetest_$$" 2>/dev/null; then
      err "Directory $d not writable"; exit 13
    fi
    rm -f "$d/.writetest_$$" || true
  done
}

migrate_legacy_library(){
  # If legacy repo library exists and target library empty, copy it.
  if [ -d "$LEGACY_LIB_IN_REPO" ] && [ -f "$LEGACY_LIB_IN_REPO/metadata.db" ]; then
    if [ ! -f "$CALIBRE_HOST_LIBRARY/metadata.db" ]; then
      log "Migrating metadata.db (and library contents) from repo library -> $CALIBRE_HOST_LIBRARY"
      rsync -a "$LEGACY_LIB_IN_REPO/" "$CALIBRE_HOST_LIBRARY/"
      if [ "$(id -u)" = "0" ]; then chown -R $APPUSER_UID:$APPUSER_GID "$CALIBRE_HOST_LIBRARY"; fi
      log "Library migration complete."\
    else
      log "Target library already has metadata.db; skipping migration."
    fi
  else
    log "No legacy repo library with metadata.db detected (skip migration)."
  fi
}

summary(){
  log "Initialization complete. Next: run scripts/ebooks_lv_setup.sh to pull images & start.";
}

main(){
  need_bins
  preflight_dirs
  migrate_legacy_library
  ensure_env
  summary
}

main "$@"
