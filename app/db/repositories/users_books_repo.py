"""Repository for user->book allow list mappings.

Thin wrapper over the existing plugin service calls. This is a transitional
adapter so higher layers can depend on repositories.* instead of directly
referencing plugin modules. Later we can move logic from services into here
and slim down services.
"""
from __future__ import annotations
from typing import Iterable, Dict, Any, List

from app.services import internal_users_books as _svc


def list_allowed_book_ids(user_id: int) -> List[int]:
    return _svc.list_user_book_ids(user_id)


def user_has_book(user_id: int, book_id: int) -> bool:
    return _svc.user_has_book(user_id, book_id)


def add_mapping(user_id: int, book_id: int) -> bool:
    return _svc.add_user_book(user_id, book_id)


def remove_mapping(user_id: int, book_id: int) -> bool:
    return _svc.remove_user_book(user_id, book_id)


def bulk_add(user_id: int, book_ids: Iterable[int]) -> Dict[str, Any]:
    return _svc.bulk_add_user_books(user_id, book_ids)


def upsert(user_id: int, book_ids: Iterable[int]) -> Dict[str, Any]:
    return _svc.upsert_user_books(user_id, book_ids)

__all__ = [
    "list_allowed_book_ids",
    "user_has_book",
    "add_mapping",
    "remove_mapping",
    "bulk_add",
    "upsert",
]
