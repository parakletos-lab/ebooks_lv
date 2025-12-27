"""Archived books helpers.

This service provides read-only access to the per-user archived-books state stored
in Calibre-Web's users DB (ub.ArchivedBook).

Used to render archived purchased books on the My Books page.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Optional, Set

from app.utils.logging import get_logger

LOG = get_logger("archived_books_service")


def list_archived_book_ids_for_user(calibre_user_id: Optional[int]) -> Set[int]:
    if calibre_user_id is None:
        return set()
    try:
        from cps import ub  # type: ignore

        archived_rows = (
            ub.session.query(ub.ArchivedBook)
            .filter(ub.ArchivedBook.user_id == int(calibre_user_id))
            .filter(ub.ArchivedBook.is_archived == True)
            .all()
        )
        out: Set[int] = set()
        for row in archived_rows:
            try:
                out.add(int(getattr(row, "book_id", None)))
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        LOG.debug("Failed to list archived book ids", exc_info=True)
        return set()


def list_archived_purchased_entries(
    *,
    calibre_user_id: Optional[int],
    purchased_book_ids: Iterable[int],
) -> List[Any]:
    """Return Calibre-Web "entries" objects for archived & purchased books.

    The returned list is suitable for rendering cards similar to Calibre-Web's
    index page (each entry exposes `entry.Books`).
    """

    if calibre_user_id is None:
        return []

    purchased: Set[int] = set()
    for bid in purchased_book_ids:
        try:
            purchased.add(int(bid))
        except (TypeError, ValueError):
            continue
    if not purchased:
        return []

    archived_ids = list_archived_book_ids_for_user(calibre_user_id)
    target_ids = sorted(purchased.intersection(archived_ids))
    if not target_ids:
        return []

    try:
        from cps import calibre_db, config as cw_config, db as cw_db  # type: ignore

        db_filter = cw_db.Books.id.in_(target_ids)
        # Use a deterministic "newest first" order for the embedded section.
        order = [cw_db.Books.timestamp.desc()]

        entries, __random, __pagination = calibre_db.fill_indexpage_with_archived_books(
            1,
            cw_db.Books,
            len(target_ids),
            db_filter,
            order,
            True,
            True,
            cw_config.config_read_column,
        )
        return list(entries or [])
    except Exception:
        LOG.debug("Failed to load archived purchased entries", exc_info=True)
        return []


__all__ = [
    "list_archived_book_ids_for_user",
    "list_archived_purchased_entries",
]
