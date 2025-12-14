#!/usr/bin/env python3
"""LEGACY (do not use).

This script existed in the plugin-era QA folder. It is kept only to avoid
breaking old references.

Use instead:
  python /app/.github/qa/scripts/bootstrap_admin.py
"""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write(
        "This script is legacy. Use /app/.github/qa/scripts/bootstrap_admin.py instead.\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
