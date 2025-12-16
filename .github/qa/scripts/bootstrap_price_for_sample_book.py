#!/usr/bin/env python3
"""Seed a deterministic Mozello price in Calibre custom column.

This enables stable UI checks for price formatting on the book details page.

Idempotent: re-running sets the same value again.
"""

from __future__ import annotations

import json

from app.services import books_sync


def main() -> int:
    book_id = 3
    price = 6.5
    ok = books_sync.set_mz_price(book_id, price)
    print(
        json.dumps(
            {
                "status": "ok" if ok else "skipped",
                "book_id": book_id,
                "mz_price": price,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
