"""Service layer.

Eventually orchestrates repositories + adapters + domain rules. For now we
reuse plugin service functions via repository wrappers as we migrate.
"""
from .users_books_service import (
    list_allowed_book_ids,
    user_has_book,
    add_mapping,
    remove_mapping,
    bulk_add,
    upsert,
)

__all__ = [
    "list_allowed_book_ids",
    "user_has_book",
    "add_mapping",
    "remove_mapping",
    "bulk_add",
    "upsert",
]
