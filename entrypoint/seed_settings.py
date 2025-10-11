#!/usr/bin/env python3
"""seed_settings.py (no-op placeholder)

Historical script removed to avoid duplicating Calibre-Web core initialization.
Upstream now solely manages settings DB, encryption key, and session key.

Kept as a stub so any external calls don't fail; logs one line and exits 0.
"""

from __future__ import annotations

import os
import sys
def main():  # pragma: no cover
    print("[SEED-SETTINGS] skipped (handled by upstream Calibre-Web core)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as se:
        raise
    except Exception:
        print("[SEED-SETTINGS] unexpected error in no-op script", file=sys.stderr)
        sys.exit(0)
