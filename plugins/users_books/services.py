"""
services.py

Business logic layer for the users_books plugin.

This module provides a clean, testable interface for manipulating the
per-user allow‑list stored in the users_books table. Higher layers
(API routes, filter hooks) should prefer calling these functions rather
than issuing raw SQLAlchemy queries directly.

Key Responsibilities:
  - CRUD-like operations on UserFilter mappings
  - Bulk helpers (add/remove/upsert)
  - Simple analytical counts (used by metrics endpoint)
  - Cache invalidation (per-request) when data changes
  - Defensive handling of duplicates based on unique constraint
    (user_id, book_id)

Design Principles:
  - Keep database session lifecycle isolated via db.plugin_session
  - Return simple Python types (bool / dict / list[int]) for easy JSON use
  - Avoid Flask imports here (pure application logic)
  - Defer logging customization to logging_setup (only import logger)

SQLAlchemy:
  - Uses select() for read operations.
  - Inserts performed by adding ORM objects.
  - Deletions performed by removing ORM instances.
  - Unique constraint ensures no duplicates; we still guard existence
    explicitly to avoid raising IntegrityError in normal flows.

Caching:
  - Per-request cache of allowed book IDs lives in cache.py.
  - After mutations (add/remove/bulk), invalidate_user_cache ensures
    subsequent reads see fresh data within the same request.

Extensibility:
  - If deny-lists or group-based rules are added, create parallel
    service functions here or a new module (e.g. group_services.py).
  - Bulk operations can be optimized (executemany) if performance
    becomes critical.

Thread Safety:
  - Each function obtains a fresh scoped session via plugin_session();
    no shared mutable state.

"""

from __future__ import annotations

from typing import Iterable, List, Dict, Any, Tuple, Sequence, Optional

from sqlalchemy import select, func

from .db import plugin_session
from .models import UserFilter
from .cache import (
    get_or_load_allowed_ids,
    invalidate_user_cache,
)

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

def list_user_book_ids(user_id: int, use_cache: bool = True) -> List[int]:
    """
    Return an ordered list of allowed book IDs for user_id.

    Parameters:
      user_id: The target user.
      use_cache: If True (default) leverage per-request cache; if False,
                 always hit the database (also updates cache).
    """
    if not use_cache:
        ids = _load_allowed_ids_from_db(user_id)
        invalidate_user_cache(user_id)  # Remove stale copy if present
        return ids
    return get_or_load_allowed_ids(user_id, _load_allowed_ids_from_db)


def user_has_book(user_id: int, book_id: int, use_cache: bool = True) -> bool:
    """
    Check quickly if the user has a mapping for the given book.

    If use_cache is True and the list is already cached, this is O(n)
    on the cached list. For extremely large lists consider a direct
    DB existence query; for now we optimize the normal small-to-medium
    sized list scenario.
    """
    if use_cache:
        cached = list_user_book_ids(user_id, use_cache=True)
        return book_id in cached
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
    invalidate_user_cache(user_id)
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
    invalidate_user_cache(user_id)
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

    if to_insert:
        invalidate_user_cache(user_id)

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

    changed = bool(to_add or to_remove)
    if changed:
        invalidate_user_cache(user_id)

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

def count_mappings() -> int:
    """Return total number of (user_id, book_id) rows."""
    with plugin_session() as s:
        return s.execute(
            select(func.count(UserFilter.id))
        ).scalar_one()


def count_distinct_users() -> int:
    """Return number of distinct users with at least one mapping."""
    with plugin_session() as s:
        return s.execute(
            select(func.count(func.distinct(UserFilter.user_id)))
        ).scalar_one()


def count_distinct_books() -> int:
    """Return number of distinct books that appear in any mapping."""
    with plugin_session() as s:
        return s.execute(
            select(func.count(func.distinct(UserFilter.book_id)))
        ).scalar_one()


def metrics_snapshot() -> Dict[str, int]:
    """
    Convenience helper returning a full metrics snapshot as a dict.
    Used by the metrics endpoint; also handy in tests.
    """
    return {
        "total_mappings": count_mappings(),
        "distinct_users": count_distinct_users(),
        "distinct_books": count_distinct_books(),
    }


# ---------------------------------------------------------------------------
# Public Export Surface
# ---------------------------------------------------------------------------

def list_distinct_book_ids(limit: int | None = None) -> List[int]:
    """
    Return an ordered (ascending) list of distinct book IDs that appear in any users_books mapping.

    Parameters:
      limit: Optional maximum number of IDs to return. If None, return all.

    Notes:
      - Uses DISTINCT + ORDER BY for deterministic ordering.
      - Intended for UI population (e.g., checkbox lists) or diagnostics.
      - If the table is large and you only need a page, supply a limit and
        add higher-level pagination later.
    """
    with plugin_session() as s:
        stmt = (
            select(UserFilter.book_id)
            .distinct()
            .order_by(UserFilter.book_id.asc())
        )
        if limit is not None and isinstance(limit, int) and limit > 0:
            stmt = stmt.limit(limit)
        rows = s.execute(stmt).all()
    return [r.book_id for r in rows]


__all__ = [
    # Read
    "list_user_book_ids",
    "user_has_book",
    "list_distinct_book_ids",
    # Single mutations
    "add_user_book",
    "remove_user_book",
    # Bulk / reconciliation
    "bulk_add_user_books",
    "upsert_user_books",
    # Metrics
    "count_mappings",
    "count_distinct_users",
    "count_distinct_books",
    "metrics_snapshot",
]
