"""
cache.py

Request-scoped caching utilities for the users_books plugin.

Goals:
  - Avoid repeated DB queries for a user's allow-list within the same HTTP request.
  - Provide a small, testable abstraction around flask.g usage.
  - Fail safe outside a Flask request context (simply bypass caching).

Design:
  - All cached data lives under a single dict stored on flask.g keyed by a constant.
  - Keys inside the dict are user_ids -> list[int] (book IDs).
  - Public helpers allow:
      * get_cached_allowed_ids(user_id)
      * set_cached_allowed_ids(user_id, ids)
      * get_or_load_allowed_ids(user_id, loader)
      * invalidate_user_cache(user_id)
      * invalidate_all_caches()
  - No direct database access here: a loader callback is injected where needed.
  - Logging kept minimal; use calling layer if deeper diagnostics required.

Usage Example (in a service or hook):
    from . import cache
    from .db import plugin_session
    from .models import UserFilter
    from sqlalchemy import select

    def load_ids(user_id: int) -> list[int]:
        with plugin_session() as s:
            rows = s.execute(
                select(UserFilter.book_id).where(UserFilter.user_id == user_id)
            ).all()
        return [r.book_id for r in rows]

    ids = cache.get_or_load_allowed_ids(user_id, load_ids)

Outside Request Context:
  - has_request_context() guards all flask.g interactions.
  - If no request context: get/set functions become no-ops (returns fresh data every call).

Thread Safety:
  - Flask's application context ensures request isolation; no extra locking needed.

Extensibility:
  - If a second cache namespace is needed (e.g., group memberships),
    add another constant key and parallel helpers.

"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional
from flask import g, has_request_context

# Internal key under which we store the per-request dictionary:
_CACHE_KEY = "_users_books_allowed_ids"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_cache_dict(create: bool = True) -> Optional[Dict[int, List[int]]]:
    """
    Return the internal cache dictionary or None if outside a request context.

    Parameters:
      create: If True and the dict does not exist, create it.

    Returns:
      Dict mapping user_id -> list of allowed book_ids, or None if not in a request.
    """
    if not has_request_context():
        return None
    cache = getattr(g, _CACHE_KEY, None)
    if cache is None and create:
        cache = {}
        setattr(g, _CACHE_KEY, cache)
    return cache


# ---------------------------------------------------------------------------
# Public cache operations
# ---------------------------------------------------------------------------

def get_cached_allowed_ids(user_id: int) -> Optional[List[int]]:
    """
    Retrieve cached allowed book IDs for a user if present; None if:
      - Not cached yet
      - Outside request context
    """
    cache = _get_cache_dict(create=False)
    if cache is None:
        return None
    return cache.get(user_id)


def set_cached_allowed_ids(user_id: int, ids: List[int]) -> None:
    """
    Store a list of allowed book IDs for the given user in the request cache.
    No-op if outside request context.
    """
    cache = _get_cache_dict(create=True)
    if cache is not None:
        cache[user_id] = ids


def get_or_load_allowed_ids(user_id: int, loader: Callable[[int], List[int]]) -> List[int]:
    """
    Return allowed book IDs for user_id, using cache if available.
    If absent (or outside request context), calls loader(user_id) and caches result when possible.

    Parameters:
      user_id: The user whose allow-list to retrieve.
      loader:  A function that fetches the list from persistent storage.

    Returns:
      List of book IDs (may be empty).
    """
    cached = get_cached_allowed_ids(user_id)
    if cached is not None:
        return cached
    ids = loader(user_id)
    set_cached_allowed_ids(user_id, ids)
    return ids


def invalidate_user_cache(user_id: int) -> None:
    """
    Remove a single user's cached allow-list entry (if present).
    No-op outside request context.
    """
    cache = _get_cache_dict(create=False)
    if cache is not None:
        cache.pop(user_id, None)


def invalidate_all_caches() -> None:
    """
    Clear the entire per-request cache dictionary.
    No-op outside request context.
    """
    if not has_request_context():
        return
    if hasattr(g, _CACHE_KEY):
        delattr(g, _CACHE_KEY)


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    "get_cached_allowed_ids",
    "set_cached_allowed_ids",
    "get_or_load_allowed_ids",
    "invalidate_user_cache",
    "invalidate_all_caches",
]
