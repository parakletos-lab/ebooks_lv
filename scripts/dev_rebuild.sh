#!/usr/bin/env bash
# dev_rebuild.sh
#
# Purpose: Fast local development rebuild + up script.
# Rebuilds the calibre-web image (optionally no-cache / pull) and
# starts (or restarts) the stack using the dev override compose file.
#
# Usage:
#   scripts/dev_rebuild.sh [--no-cache] [--pull] [--logs] [--down] [--no-dev] [--prune]
#
# Flags:
#   --no-cache  : Build without layer cache
#   --pull      : Always attempt to pull newer base layers before build
#   --logs      : Tail logs after bringing up the container
#   --down      : Force docker compose down before rebuild (clean restart)
#   --no-dev    : Do NOT include compose.dev.yml override (only base compose.yml)
#   --prune     : After successful build/start, run 'docker image prune -f' (dangling images cleanup)
#
# Examples:
#   scripts/dev_rebuild.sh --logs
#   scripts/dev_rebuild.sh --no-cache --pull --logs
#   scripts/dev_rebuild.sh --down --no-dev
#
set -euo pipefail

RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; BOLD="\033[1m"; RESET="\033[0m"

log() { echo -e "${BLUE}[dev]${RESET} $*"; }
warn() { echo -e "${YELLOW}[warn]${RESET} $*"; }
err() { echo -e "${RED}[err]${RESET} $*" >&2; }

need() { command -v "$1" >/dev/null 2>&1 || { err "Missing required binary: $1"; exit 2; }; }

need docker
need git

if ! docker compose version >/dev/null 2>&1; then
  err "docker compose plugin not found (Docker >= 20.10 + plugin required)."
  exit 2
fi

NO_CACHE=0
ALWAYS_PULL=0
TAIL_LOGS=0
DO_DOWN=0
USE_DEV=1
PRUNE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cache) NO_CACHE=1 ; shift ;;
    --pull) ALWAYS_PULL=1 ; shift ;;
    --logs) TAIL_LOGS=1 ; shift ;;
    --down) DO_DOWN=1 ; shift ;;
  --no-dev) USE_DEV=0 ; shift ;;
  --prune) PRUNE=1 ; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) err "Unknown arg: $1"; exit 1 ;;
  esac
done

COMPOSE_BASE=compose.yml
COMPOSE_DEV=compose.dev.yml

[[ -f $COMPOSE_BASE ]] || { err "Missing $COMPOSE_BASE in repo root"; exit 3; }
if [[ $USE_DEV -eq 1 && ! -f $COMPOSE_DEV ]]; then
  warn "Dev override $COMPOSE_DEV not found; proceeding with base only"; USE_DEV=0
fi

COMPOSE_FILES=(-f "$COMPOSE_BASE")
[[ $USE_DEV -eq 1 ]] && COMPOSE_FILES+=(-f "$COMPOSE_DEV")

SERVICE=calibre-web

if [[ $DO_DOWN -eq 1 ]]; then
  log "Bringing stack down (clean restart)"
  docker compose "${COMPOSE_FILES[@]}" down --remove-orphans || true
fi

log "Ensuring submodule(s) up-to-date"
git submodule update --init --recursive

BUILD_ARGS=(build)
[[ $NO_CACHE -eq 1 ]] && BUILD_ARGS+=(--no-cache)
[[ $ALWAYS_PULL -eq 1 ]] && BUILD_ARGS+=(--pull)

log "Building image ($SERVICE)"
docker compose "${COMPOSE_FILES[@]}" "${BUILD_ARGS[@]}" $SERVICE

log "Starting / updating container"
docker compose "${COMPOSE_FILES[@]}" up -d $SERVICE

if [[ $PRUNE -eq 1 ]]; then
  log "Pruning dangling images (docker image prune -f)"
  docker image prune -f || warn "Image prune failed"
fi

if [[ $TAIL_LOGS -eq 1 ]]; then
  log "Tailing logs (Ctrl+C to exit)"
  docker compose "${COMPOSE_FILES[@]}" logs -f $SERVICE
else
  log "Done. Use: docker compose ${COMPOSE_FILES[*]} logs -f $SERVICE"
fi
