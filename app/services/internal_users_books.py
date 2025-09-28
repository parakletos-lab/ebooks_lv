"""Internal implementation of users_books business logic (migrated).

Derived from plugins.users_books.services (simplified, no cache layer).
"""
from __future__ import annotations
from typing import Iterable, List, Dict, Any
from sqlalchemy import select

from app.db import plugin_session
from app.db.models import UserFilter


def _load_allowed_ids_from_db(user_id: int) -> List[int]:
    with plugin_session() as s:
        rows = s.execute(
            select(UserFilter.book_id)
            .where(UserFilter.user_id == user_id)
            .order_by(UserFilter.book_id.asc())
        ).all()
    return [r.book_id for r in rows]


def _exists(user_id: int, book_id: int) -> bool:
    with plugin_session() as s:
        hit = s.execute(
            select(UserFilter.id)
            .where(UserFilter.user_id == user_id, UserFilter.book_id == book_id)
        ).first()
    return bool(hit)


def list_user_book_ids(user_id: int) -> List[int]:
    return _load_allowed_ids_from_db(user_id)


def user_has_book(user_id: int, book_id: int) -> bool:
    return _exists(user_id, book_id)


def add_user_book(user_id: int, book_id: int) -> bool:
    with plugin_session() as s:
        already = s.execute(
            select(UserFilter.id).where(
                UserFilter.user_id == user_id,
                UserFilter.book_id == book_id,
            )
        ).first()
        if already:
            return False
        s.add(UserFilter(user_id=user_id, book_id=book_id))
    return True


def remove_user_book(user_id: int, book_id: int) -> bool:
    with plugin_session() as s:
        row = s.execute(
            select(UserFilter).where(
                UserFilter.user_id == user_id,
                UserFilter.book_id == book_id,
            )
        ).scalar_one_or_none()
        if not row:
            return False
        s.delete(row)
    return True


def bulk_add_user_books(user_id: int, book_ids: Iterable[int]) -> Dict[str, Any]:
    unique_ids: List[int] = sorted({int(b) for b in book_ids})
    if not unique_ids:
        return {"requested": 0, "added": 0, "skipped_existing": 0, "book_ids_added": [], "book_ids_existing": []}
    existing: set[int] = set()
    to_insert: List[int] = []
    with plugin_session() as s:
        rows = s.execute(
            select(UserFilter.book_id).where(
                UserFilter.user_id == user_id,
                UserFilter.book_id.in_(unique_ids),
            )
        ).all()
        existing = {r.book_id for r in rows}
        for bid in unique_ids:
            if bid in existing:
                continue
            s.add(UserFilter(user_id=user_id, book_id=bid))
            to_insert.append(bid)
    return {
        "requested": len(unique_ids),
        "added": len(to_insert),
        "skipped_existing": len(existing),
        "book_ids_added": to_insert,
        "book_ids_existing": sorted(existing),
    }


def upsert_user_books(user_id: int, desired_book_ids: Iterable[int]) -> Dict[str, Any]:
    target_ids = {int(b) for b in desired_book_ids}
    with plugin_session() as s:
        current_rows = s.execute(select(UserFilter.book_id).where(UserFilter.user_id == user_id)).all()
        current_ids = {r.book_id for r in current_rows}
        to_add = sorted(target_ids - current_ids)
        to_remove = sorted(current_ids - target_ids)
        for bid in to_add:
            s.add(UserFilter(user_id=user_id, book_id=bid))
        if to_remove:
            doomed_rows = s.execute(
                select(UserFilter).where(
                    UserFilter.user_id == user_id,
                    UserFilter.book_id.in_(to_remove),
                )
            ).scalars().all()
            for row in doomed_rows:
                s.delete(row)
    final_total = len(target_ids)
    return {
        "desired": len(target_ids),
        "added": len(to_add),
        "removed": len(to_remove),
        "final_total": final_total,
        "added_ids": to_add,
        "removed_ids": to_remove,
    }

__all__ = [
    "list_user_book_ids",
    "user_has_book",
    "add_user_book",
    "remove_user_book",
    "bulk_add_user_books",
    "upsert_user_books",
]
