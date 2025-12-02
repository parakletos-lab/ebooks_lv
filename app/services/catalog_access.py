"""Per-request catalog access helpers for non-admin users."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Set

from app.db.repositories import users_books_repo
from app.services import books_sync
from app.utils.identity import normalize_email


class BookState(str, Enum):
    """Supported catalog states for rendered books."""

    PURCHASED = "purchased"
    AVAILABLE = "available"


@dataclass(frozen=True)
class UserCatalogState:
    """Book access metadata resolved for the active request."""

    is_admin: bool
    is_authenticated: bool = False
    purchased_book_ids: Set[int] = field(default_factory=set)

    def is_purchased(self, book_id: Optional[int]) -> bool:
        if book_id is None:
            return False
        try:
            candidate = int(book_id)
        except (TypeError, ValueError):
            return False
        return candidate in self.purchased_book_ids

    def book_state(self, book_id: Optional[int]) -> BookState:
        return BookState.PURCHASED if self.is_purchased(book_id) else BookState.AVAILABLE

    def to_payload(self) -> Dict[str, Any]:
        return {
            "mode": "admin" if self.is_admin else "non_admin",
            "authenticated": self.is_authenticated,
            "purchased": sorted(self.purchased_book_ids),
        }


def build_catalog_state(
    *,
    calibre_user_id: Optional[int],
    email: Optional[str],
    is_admin: bool,
) -> UserCatalogState:
    if is_admin:
        return UserCatalogState(is_admin=True, is_authenticated=True)

    normalized_email = normalize_email(email)
    is_authenticated = calibre_user_id is not None
    orders = users_books_repo.list_orders_for_user(
        calibre_user_id=calibre_user_id,
        email=normalized_email,
    )
    purchased_ids: Set[int] = set()
    handles_missing: Set[str] = set()
    for order in orders:
        book_id = getattr(order, "calibre_book_id", None)
        if book_id is None:
            handle = getattr(order, "mz_handle", None)
            if isinstance(handle, str) and handle.strip():
                handles_missing.add(handle.strip())
            continue
        try:
            purchased_ids.add(int(book_id))
        except (TypeError, ValueError):
            continue

    if handles_missing:
        lookup_results = books_sync.lookup_books_by_handles(handles_missing)
        for handle in handles_missing:
            info = lookup_results.get(handle.strip().lower()) if handle else None
            book_id = info.get("book_id") if isinstance(info, dict) else None
            try:
                if book_id is not None:
                    purchased_ids.add(int(book_id))
            except (TypeError, ValueError):
                continue

    state = UserCatalogState(
        is_admin=False,
        is_authenticated=is_authenticated,
        purchased_book_ids=purchased_ids,
    )

    return state


__all__ = [
    "BookState",
    "UserCatalogState",
    "build_catalog_state",
]
