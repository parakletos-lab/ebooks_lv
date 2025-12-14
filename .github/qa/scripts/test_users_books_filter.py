#!/usr/bin/env python3
"""LEGACY (do not use).

This script depended on the retired users_books allow-list plugin.

Current mechanism is Mozello orders -> catalog overrides.
See `.github/qa/e2e/non_admin_catalog_scope.md`.
"""
from __future__ import annotations

import sys


def main() -> int:
    sys.stderr.write("Legacy script; see .github/qa/e2e/non_admin_catalog_scope.md\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
