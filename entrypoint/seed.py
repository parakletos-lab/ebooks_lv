#!/usr/bin/env python3
"""Seeding orchestrator.

Runs all individual seed_xxx routines (settings + library) in a controlled,
idempotent order producing concise one‑line success logs per seed.

Exit Codes:
  0 = all ok / or already present
  3 = one or more seed steps failed (non-fatal for manual invocation)
"""
from __future__ import annotations

import sys


def _run_library() -> bool:
    try:
        from entrypoint import seed_library  # type: ignore
        summary = seed_library.ensure_mz_price_column()
        if summary.get("error"):
            print(f"[SEED] library ERROR {summary['error']}", file=sys.stderr)
            return False
        print(
            f"[SEED] library ok mz_price_id={summary.get('id')} created={'yes' if summary.get('created') else 'no'} values={summary.get('values')}"
        )
        return True
    except Exception as exc:  # pragma: no cover
        print(f"[SEED] library ERROR {exc}", file=sys.stderr)
        return False


def main() -> int:  # pragma: no cover (thin wrapper)
    # Only library seeding retained (price column); Calibre-Web core handles its own settings.
    ok_library = _run_library()
    return 0 if ok_library else 3


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
