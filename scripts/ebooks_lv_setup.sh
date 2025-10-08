#!/usr/bin/env bash
# Interactive (idempotent) setup script for ebooks_lv deployment on a droplet.
# Safe to re-run when new env vars are introduced or configuration changes.
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
REQUIRED_BIN=(docker docker compose git)

log() { echo "[setup] $*"; }
err() { echo "[setup][error] $*" >&2; }

need_bins() {
  local missing=0
  for b in "${REQUIRED_BIN[@]}"; do
    if ! command -v $b >/dev/null 2>&1; then
      err "Missing required binary: $b"; missing=1
    fi
  done
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

pull_images() {
  if docker compose $COMPOSE_FILES pull; then
    log "Images pulled (if already present)."
  else
    log "Pull failed (might build locally)." 
  fi
}

start_stack() {
  log "Starting stack..."
  docker compose $COMPOSE_FILES up -d
  log "Stack started. Use 'docker compose $COMPOSE_FILES ps' to inspect."
}

health_check() {
  sleep 3
  local container
  container=$(docker compose $COMPOSE_FILES ps --services | head -n1)
  if [ -n "$container" ]; then
    local name
    name=$(docker compose $COMPOSE_FILES ps -q "$container")
    if [ -n "$name" ]; then
      log "Recent logs (tail 20):"
      docker logs --tail 20 "$name" || true
    fi
  fi
}

main() {
  need_bins
  # Optional: update code if this script runs from a cloned repo and user wants to update
  if [[ -d "$REPO_ROOT/.git" ]]; then
    log "Updating code from git (fast-forward if possible)..."
    if ! git -C "$REPO_ROOT" fetch --all --prune; then log "git fetch failed (continuing)"; fi
    if ! git -C "$REPO_ROOT" pull --ff-only; then log "git pull failed or non-ff (continuing)"; fi
    if [[ -f "$REPO_ROOT/.gitmodules" ]]; then
      log "Syncing submodules..."
      git -C "$REPO_ROOT" submodule sync --recursive || true
      git -C "$REPO_ROOT" submodule update --init --recursive || log "submodule update issues (continuing)"
    fi
  fi
  ensure_env_file
  log "Collecting / updating required environment variables..."
  prompt_env_var MOZELLO_API_KEY "Mozello API key used by backend" ""
  prompt_env_var TZ "System timezone (IANA)" "Europe/Riga"
  # Future vars can be added here safely; script is re-runnable.

  summary_env
  pull_images
  start_stack
  health_check
  log "Setup complete. Re-run this script anytime to modify environment variables or pull newer images."
}

main "$@"
