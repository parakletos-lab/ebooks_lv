"""Users-books service façade.

Temporary pass-through to repository & legacy plugin logic. This lets future
code import from app.services without depending on plugin namespace.
"""
from __future__ import annotations
from typing import Iterable, Dict, Any, List

from app.services import internal_users_books as impl


def list_allowed_book_ids(user_id: int) -> List[int]:
    return impl.list_user_book_ids(user_id)


def user_has_book(user_id: int, book_id: int) -> bool:
    return impl.user_has_book(user_id, book_id)


def add_mapping(user_id: int, book_id: int) -> bool:
    return impl.add_user_book(user_id, book_id)


def remove_mapping(user_id: int, book_id: int) -> bool:
    return impl.remove_user_book(user_id, book_id)


def bulk_add(user_id: int, book_ids: Iterable[int]) -> Dict[str, Any]:
    return impl.bulk_add_user_books(user_id, book_ids)


def upsert(user_id: int, book_ids: Iterable[int]) -> Dict[str, Any]:
    return impl.upsert_user_books(user_id, book_ids)

__all__ = [
    "list_allowed_book_ids",
    "user_has_book",
    "add_mapping",
    "remove_mapping",
    "bulk_add",
    "upsert",
]
