#!/usr/bin/env python3
"""Seed deterministic Mozello pictures identifiers for a sample book.

This enables stable UI checks for the book-details additional images gallery.

Idempotent: re-running sets the same values again.
"""

from __future__ import annotations

import json

from app.services import books_sync


def main() -> int:
    book_id = 3

    # One picture is treated as the cover (filtered out from thumbnail strip).
    cover_uid = "qa_cover_uid"

    pictures = [
        {"uid": cover_uid, "url": "/static/img/fullscreen.png"},
        {"uid": "qa_extra_uid_1", "url": "/static/img/menu-icon.png"},
        {"uid": "qa_extra_uid_2", "url": "/static/img/settings.png"},
        # External Mozello-hosted examples (used to verify CSP img-src allow-listing).
        {
            "uid": "qa_extra_uid_3",
            "url": "https://site-2796926.mozfiles.com/files/2796926/catitems/l/calibre-cover-eae7aefdfb4a6c237e76b7a3db0d8d16-f621567a.jpg?7825642",
        },
        {
            "uid": "qa_extra_uid_4",
            "url": "https://site-2796926.mozfiles.com/files/2796926/catitems/l/cover-d55bf78aaa09593d7f415e0c985a2669-e719942d.jpg?7779842",
        },
        {
            "uid": "qa_extra_uid_5",
            "url": "https://site-2796926.mozfiles.com/files/2796926/catitems/l/16x16-icon-45594-c8569125.png?7825644",
        },
    ]

    ok_cover = books_sync.set_mz_cover_picture_uids(book_id, [cover_uid])
    ok_pics = books_sync.set_mz_pictures(book_id, pictures)

    print(
        json.dumps(
            {
                "status": "ok" if (ok_cover and ok_pics) else "skipped",
                "book_id": book_id,
                "mz_cover_uids": [cover_uid],
                "mz_pictures": pictures,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
