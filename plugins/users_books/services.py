"""Minimal service layer for users_books plugin.

Kept scope (per user request):
    - List a user's allowed book IDs.
    - Add/remove single mappings.
    - Bulk add mappings.
    - Upsert (reconcile) full set.

All metrics, caching and auxiliary analytical helpers removed.
"""

from __future__ import annotations

from typing import Iterable, List, Dict, Any

from sqlalchemy import select

from .db import plugin_session
from .models import UserFilter
from .logging_setup import get_logger

LOG = get_logger()


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _load_allowed_ids_from_db(user_id: int) -> List[int]:
    """Internal loader used with get_or_load_allowed_ids."""
    with plugin_session() as s:
        rows = s.execute(
            select(UserFilter.book_id)
            .where(UserFilter.user_id == user_id)
            .order_by(UserFilter.book_id.asc())
        ).all()
    return [r.book_id for r in rows]


def _exists(user_id: int, book_id: int) -> bool:
    """Return True if a mapping already exists."""
    with plugin_session() as s:
        hit = s.execute(
            select(UserFilter.id)
            .where(
                UserFilter.user_id == user_id,
                UserFilter.book_id == book_id,
            )
        ).first()
    return bool(hit)


# ---------------------------------------------------------------------------
# Query / Read Operations
# ---------------------------------------------------------------------------

def list_user_book_ids(user_id: int, use_cache: bool = True) -> List[int]:  # use_cache retained for backward compat
    """Return ordered list of allowed book IDs for the user (no caching)."""
    return _load_allowed_ids_from_db(user_id)


def user_has_book(user_id: int, book_id: int, use_cache: bool = True) -> bool:
    """Return True if mapping exists (no cache)."""
    return _exists(user_id, book_id)


# ---------------------------------------------------------------------------
# Mutation Operations (Single)
# ---------------------------------------------------------------------------

def add_user_book(user_id: int, book_id: int) -> bool:
    """
    Add a (user_id, book_id) mapping if it doesn't already exist.

    Returns:
      True  -> mapping was created
      False -> mapping already existed
    """
    with plugin_session() as s:
        # Existence check first to avoid IntegrityError on UNIQUE constraint.
        already = s.execute(
            select(UserFilter.id).where(
                UserFilter.user_id == user_id,
                UserFilter.book_id == book_id
            )
        ).first()
        if already:
            return False
        s.add(UserFilter(user_id=user_id, book_id=book_id))
    # No cache layer
    return True


def remove_user_book(user_id: int, book_id: int) -> bool:
    """
    Remove a mapping if present.

    Returns:
      True  -> mapping deleted
      False -> no such mapping
    """
    with plugin_session() as s:
        row = s.execute(
            select(UserFilter).where(
                UserFilter.user_id == user_id,
                UserFilter.book_id == book_id
            )
        ).scalar_one_or_none()
        if not row:
            return False
        s.delete(row)
    # No cache layer
    return True


# ---------------------------------------------------------------------------
# Bulk Operations
# ---------------------------------------------------------------------------

def bulk_add_user_books(user_id: int, book_ids: Iterable[int]) -> Dict[str, Any]:
    """
    Add multiple book IDs to a user's allow-list.

    Parameters:
      user_id: Target user.
      book_ids: Iterable of integer book IDs (may contain duplicates).

    Returns:
      {
        "requested": <int>,   # total IDs provided (after normalization & dedupe)
        "added": <int>,       # new mappings actually inserted
        "skipped_existing": <int>, # IDs that were already present
        "book_ids_added": [ ... ], # list of IDs inserted
        "book_ids_existing": [ ... ] # list of IDs already mapped
      }
    """
    # Normalize & deduplicate early
    unique_ids: List[int] = sorted({int(b) for b in book_ids})
    if not unique_ids:
        return {
            "requested": 0,
            "added": 0,
            "skipped_existing": 0,
            "book_ids_added": [],
            "book_ids_existing": [],
        }

    existing: set[int] = set()
    to_insert: List[int] = []

    with plugin_session() as s:
        # Fetch existing mappings in one query
        rows = s.execute(
            select(UserFilter.book_id)
            .where(
                UserFilter.user_id == user_id,
                UserFilter.book_id.in_(unique_ids)
            )
        ).all()
        existing = {r.book_id for r in rows}

        for bid in unique_ids:
            if bid in existing:
                continue
            s.add(UserFilter(user_id=user_id, book_id=bid))
            to_insert.append(bid)

    # No cache layer

    return {
        "requested": len(unique_ids),
        "added": len(to_insert),
        "skipped_existing": len(existing),
        "book_ids_added": to_insert,
        "book_ids_existing": sorted(existing),
    }


def upsert_user_books(user_id: int, desired_book_ids: Iterable[int]) -> Dict[str, Any]:
    """
    Perform a reconciliation so that the user's allow-list matches exactly
    the set of desired_book_ids.

    Steps:
      1. Determine current set.
      2. Insert missing entries.
      3. Remove obsolete entries.

    Returns:
      {
        "desired": <int>,
        "added": <int>,
        "removed": <int>,
        "final_total": <int>,
        "added_ids": [...],
        "removed_ids": [...]
      }

    NOTE:
      - For very large sets, consider more efficient batch methods.
      - This will invalidate cache only once if any change occurs.
    """
    target_ids = {int(b) for b in desired_book_ids}
    with plugin_session() as s:
        current_rows = s.execute(
            select(UserFilter.book_id).where(UserFilter.user_id == user_id)
        ).all()
        current_ids = {r.book_id for r in current_rows}

        to_add = sorted(target_ids - current_ids)
        to_remove = sorted(current_ids - target_ids)

        # Insert new mappings
        for bid in to_add:
            s.add(UserFilter(user_id=user_id, book_id=bid))

        # Remove obsolete
        if to_remove:
            # Efficient delete by IN clause
            doomed_rows = s.execute(
                select(UserFilter)
                .where(
                    UserFilter.user_id == user_id,
                    UserFilter.book_id.in_(to_remove)
                )
            ).scalars().all()
            for row in doomed_rows:
                s.delete(row)

    # No cache layer

    final_total = len(target_ids)
    return {
        "desired": len(target_ids),
        "added": len(to_add),
        "removed": len(to_remove),
        "final_total": final_total,
        "added_ids": to_add,
        "removed_ids": to_remove,
    }


# ---------------------------------------------------------------------------
# Analytical / Metrics Helpers
# ---------------------------------------------------------------------------

__all__ = [
    "list_user_book_ids",
    "user_has_book",
    "add_user_book",
    "remove_user_book",
    "bulk_add_user_books",
    "upsert_user_books",
]
