#!/usr/bin/env bash
set -euo pipefail

# Conservative host-level log cleanup for Ubuntu/Debian droplets.
# This does NOT touch Docker images/volumes/containers.
#
# Safe to run periodically (e.g., weekly).

if command -v journalctl >/dev/null 2>&1; then
  # Keep up to ~30 days of journal logs (whichever is smaller in practice).
  journalctl --vacuum-time=30d || true

  # Also cap the journal by size as a second guardrail.
  journalctl --vacuum-size=500M || true
fi

# Optional: rotate apt logs via built-in logrotate (usually already installed).
if command -v logrotate >/dev/null 2>&1 && [ -f /etc/logrotate.conf ]; then
  logrotate -f /etc/logrotate.conf || true
fi
