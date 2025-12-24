#!/usr/bin/env bash
# Interactive (idempotent) setup script for ebooks_lv deployment on a droplet.
# Safe to re-run when new env vars are introduced or configuration changes.

if [ -z "${BASH_VERSION:-}" ]; then
  echo "[setup][error] This script must be run with bash (e.g. 'bash ./scripts/ebooks_lv_setup.sh')." >&2
  exit 1
fi

set -euo pipefail

# App root: if running from a cloned repo, prefer its parent as runtime dir; else fallback
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_DIR="${APP_DIR:-/opt/ebooks_lv}"
# If this repo is already under /opt/ebooks_lv, respect that path
if [[ -d "$REPO_ROOT/.git" && "$REPO_ROOT" != "/" ]]; then
  APP_DIR="${APP_DIR:-$REPO_ROOT}"
fi
ENV_FILE="${APP_DIR}/.env"
COMPOSE_FILES="-f compose.yml -f compose.droplet.yml"
REQUIRED_BIN=(docker git)
COMPOSE_CMD=""

CALIBRE_HOST_CONFIG="/opt/calibre/config"
BACKUP_DIR="${CALIBRE_HOST_CONFIG}/backups"
BACKUP_KEEP=5

log() { echo "[setup] $*"; }
err() { echo "[setup][error] $*" >&2; }

need_bins() {
  local missing=0
  for b in "${REQUIRED_BIN[@]}"; do
    if ! command -v $b >/dev/null 2>&1; then
      err "Missing required binary: $b"; missing=1
    fi
  done
  # Resolve docker compose command (plugin preferred)
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  else
    err "Missing required binary: docker compose (plugin) or docker-compose"
    err "Install docker compose plugin: 'sudo apt-get update && sudo apt-get install -y docker-compose-plugin'"
    err "Or install legacy: 'sudo curl -L https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-$(uname -s)-$(uname -m) -o /usr/local/bin/docker-compose && sudo chmod +x /usr/local/bin/docker-compose'"
    missing=1
  fi
  if [ -n "$COMPOSE_CMD" ]; then
    log "Using compose command: $COMPOSE_CMD"
  fi
  if [ $missing -eq 1 ]; then
    err "Install missing dependencies then re-run."; exit 1
  fi
}

prompt_env_var() {
  local key="$1"; shift
  local desc="$1"; shift || true
  local default="${1:-}"; shift || true
  local current=""
  if [ -f "$ENV_FILE" ]; then
    current=$(grep -E "^${key}=" "$ENV_FILE" | sed -E "s/^${key}=//") || true
  fi
  if [ -n "$current" ]; then
    echo "$key is currently set. Leave blank to keep (value hidden)."
  fi
  local prompt="${key} (${desc})"
  [ -n "$default" ] && prompt+=" [${default}]"
  prompt+=" : "
  read -r -p "$prompt" input || true
  if [ -z "$input" ]; then
    if [ -n "$current" ]; then
      log "Keeping existing $key"
      return 0
    fi
    if [ -n "$default" ]; then
      input="$default"
    else
      err "$key is required."; prompt_env_var "$key" "$desc" "$default"; return 0
    fi
  fi
  # Escape any existing slashes/newlines
  input=${input//$'\n'/}
  # Append or replace in .env
  if [ -f "$ENV_FILE" ] && grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i.bak -E "s|^${key}=.*|${key}=${input}|" "$ENV_FILE"
  else
    echo "${key}=${input}" >> "$ENV_FILE"
  fi
}

ensure_env_file() {
  if [ ! -f "$ENV_FILE" ]; then
    log "Creating new env file at $ENV_FILE"
    mkdir -p "${APP_DIR}" && touch "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi
}

summary_env() {
  log "Current .env:" 
  grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | sed 's/=.*/=***hidden***/'
}

require_env_var() {
  local key="$1"
  if ! grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    err "$key is missing from $ENV_FILE. Run ebooks_lv_init.sh or edit the file to set it before continuing."
    exit 1
  fi
}

pull_images() {
  if $COMPOSE_CMD $COMPOSE_FILES pull; then
    log "Images pulled (if already present)."
  else
    log "Pull failed (might build locally)." 
  fi
}

start_stack() {
  log "Starting stack..."
  $COMPOSE_CMD $COMPOSE_FILES up -d
  log "Stack started. Use '$COMPOSE_CMD $COMPOSE_FILES ps' to inspect."
}

health_check() {
  sleep 3
  local container
  container=$($COMPOSE_CMD $COMPOSE_FILES ps --services | head -n1)
  if [ -n "$container" ]; then
    local name
    name=$($COMPOSE_CMD $COMPOSE_FILES ps -q "$container")
    if [ -n "$name" ]; then
      log "Recent logs (tail 20):"
      docker logs --tail 20 "$name" || true
    fi
  fi
}

ensure_backup_dir() {
  if [ -e "$BACKUP_DIR" ] && [ ! -d "$BACKUP_DIR" ]; then
    err "Backup path exists but is not a directory: $BACKUP_DIR"
    exit 12
  fi
  mkdir -p "$BACKUP_DIR"
}

prune_old_backups() {
  # Keep the most recent $BACKUP_KEEP backups (by mtime).
  local backups=()
  local i
  while IFS= read -r line; do
    [ -n "$line" ] && backups+=("$line")
  done < <(ls -1t "$BACKUP_DIR"/config_backup_*.tar.gz 2>/dev/null || true)

  if [ "${#backups[@]}" -le "$BACKUP_KEEP" ]; then
    return 0
  fi

  for ((i=BACKUP_KEEP; i<${#backups[@]}; i++)); do
    log "Pruning old backup: ${backups[$i]}"
    rm -f "${backups[$i]}" || true
  done
}

maybe_backup_config_for_version() {
  local version="$1"
  if [ -z "$version" ]; then
    log "No target version resolved; skipping config backup"
    return 0
  fi
  if [ ! -d "$CALIBRE_HOST_CONFIG" ]; then
    log "Config dir not found ($CALIBRE_HOST_CONFIG); skipping backup"
    return 0
  fi

  ensure_backup_dir
  local dest="$BACKUP_DIR/config_backup_${version}.tar.gz"

  # Idempotency: one backup per target version.
  if [ -f "$dest" ]; then
    log "Config backup already exists for version $version (skip): $dest"
    return 0
  fi

  log "Creating config backup for version $version -> $dest"
  # Exclude backups to avoid recursive archives.
  tar -C "$CALIBRE_HOST_CONFIG" --exclude='./backups' -czf "$dest" .
  prune_old_backups
}


main() {
  need_bins
  # Optional: update code if this script runs from a cloned repo and user wants to update
  if [[ -d "$REPO_ROOT/.git" ]]; then
    log "Updating code from git (fast-forward if possible)..."
    if git -C "$REPO_ROOT" fetch --all --prune; then
      # If a fast-forward update is available, take a config backup keyed by the *target* git version.
      # This is idempotent: a backup is created only once per target version.
      current_version="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || true)"
      target_version="$(git -C "$REPO_ROOT" rev-parse --short '@{u}' 2>/dev/null || true)"
      if [ -n "$target_version" ] && [ -n "$current_version" ] && [ "$target_version" != "$current_version" ]; then
        maybe_backup_config_for_version "$target_version"
      else
        log "No upstream fast-forward detected; skipping config backup"
      fi
    else
      log "git fetch failed (continuing)"
    fi

    if ! git -C "$REPO_ROOT" pull --ff-only; then log "git pull failed or non-ff (continuing)"; fi
    if [[ -f "$REPO_ROOT/.gitmodules" ]]; then
      log "Syncing submodules..."
      git -C "$REPO_ROOT" submodule sync --recursive || true
      git -C "$REPO_ROOT" submodule update --init --recursive || log "submodule update issues (continuing)"
    fi
  fi
  ensure_env_file
  log "Ensuring required environment variables are present (interactive prompts run during init)."
  require_env_var "TZ"
  # EBOOKSLV_DOMAIN is only required when using the HTTPS Caddy overlay
  # (compose.droplet.caddy.yml). The default droplet stack runs HTTP-only.
  # Future vars can be added here safely; script is re-runnable.

  summary_env
  pull_images
  start_stack
  health_check
  log "Setup complete. Re-run this script anytime to modify environment variables or pull newer images."
}

main "$@"
