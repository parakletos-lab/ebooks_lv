#!/usr/bin/env python3
"""LEGACY (do not use).

Use instead:
  python /app/.github/qa/scripts/bootstrap_non_admin_user.py
"""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write(
        "This script is legacy. Use /app/.github/qa/scripts/bootstrap_non_admin_user.py instead.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
