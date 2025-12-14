#!/usr/bin/env python3
"""LEGACY (do not use).

This script depended on the retired users_books allow-list plugin.

Current mechanism: Mozello orders (users_books DB) -> catalog overrides.
Use:
  python /app/.github/qa/scripts/bootstrap_order_for_non_admin.py
"""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write(
        "Legacy script. Use /app/.github/qa/scripts/bootstrap_order_for_non_admin.py instead.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

