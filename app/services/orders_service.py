"""Mozello orders service orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.db.models import MozelloOrder
from app.db.repositories import users_books_repo
from app.db.repositories.users_books_repo import OrderExistsError as RepoOrderExistsError
from app.services import books_sync
from app.services.calibre_users_service import (
    CalibreUnavailableError,
    UserAlreadyExistsError,
    create_user_for_email,
    lookup_user_by_email,
    lookup_users_by_emails,
)
from app.utils.identity import normalize_email
from app.utils.logging import get_logger

LOG = get_logger("orders_service")


class OrderValidationError(ValueError):
    """Raised when order payload fails validation."""


class OrderAlreadyExistsError(RuntimeError):
    """Raised when attempting to create a duplicate order."""


class OrderNotFoundError(RuntimeError):
    """Raised when an order id cannot be located."""


@dataclass
class OrderView:
    id: int
    email: str
    mz_handle: str
    calibre_book: Optional[Dict[str, Any]]
    calibre_user: Optional[Dict[str, Any]]
    book_error: Optional[str]
    user_missing: bool
    created_at: Optional[str]
    updated_at: Optional[str]


def _order_to_view(
    order: MozelloOrder,
    book: Optional[Dict[str, Any]],
    user: Optional[Dict[str, Any]],
) -> OrderView:
    book_error = None if book else f"Calibre book not found for handle '{order.mz_handle}'"
    return OrderView(
        id=order.id,
        email=order.email,
        mz_handle=order.mz_handle,
        calibre_book=book,
        calibre_user=user,
        book_error=book_error,
        user_missing=user is None,
        created_at=order.created_at.isoformat() if order.created_at else None,
        updated_at=order.updated_at.isoformat() if order.updated_at else None,
    )


def list_orders() -> Dict[str, Any]:
    orders = users_books_repo.list_orders()
    if not orders:
        return {"orders": [], "summary": {"total": 0, "linked_books": 0, "linked_users": 0}}

    handles = {o.mz_handle.lower() for o in orders if o.mz_handle}
    emails = {normalize_email(o.email) for o in orders if normalize_email(o.email)}

    book_map = books_sync.lookup_books_by_handles(handles)
    user_map = lookup_users_by_emails(emails)

    pending_updates: Dict[int, Dict[str, Optional[int]]] = {}
    views: List[OrderView] = []

    for order in orders:
        key_handle = order.mz_handle.lower() if order.mz_handle else ""
        book_info = book_map.get(key_handle)
        email_key = normalize_email(order.email)
        user_info = user_map.get(email_key) if email_key else None

        update_entry = pending_updates.setdefault(order.id, {"user": None, "book": None})
        if book_info and order.calibre_book_id != book_info.get("book_id"):
            update_entry["book"] = book_info.get("book_id")
        if user_info and order.calibre_user_id != user_info.get("id"):
            update_entry["user"] = user_info.get("id")

        views.append(_order_to_view(order, book_info, user_info))

    updates = []
    for order_id, payload in pending_updates.items():
        if payload["user"] is None and payload["book"] is None:
            continue
        updates.append((order_id, payload["user"], payload["book"]))
    if updates:
        users_books_repo.bulk_update_links(updates)

    summary = {
        "total": len(orders),
        "linked_books": sum(1 for v in views if v.calibre_book),
        "linked_users": sum(1 for v in views if not v.user_missing),
    }
    return {"orders": [v.__dict__ for v in views], "summary": summary}


def create_order(email: str, mz_handle: str) -> Dict[str, Any]:
    normalized_email = normalize_email(email)
    if not normalized_email:
        raise OrderValidationError("email_required")
    handle_clean = (mz_handle or "").strip()
    if not handle_clean:
        raise OrderValidationError("mz_handle_required")

    book_lookup = books_sync.lookup_books_by_handles({handle_clean.lower()})
    book_info = book_lookup.get(handle_clean.lower())

    user_info = lookup_user_by_email(normalized_email)

    try:
        order = users_books_repo.create_order(
            normalized_email,
            handle_clean,
            calibre_user_id=user_info.get("id") if user_info else None,
            calibre_book_id=book_info.get("book_id") if book_info else None,
        )
    except RepoOrderExistsError as exc:
        raise OrderAlreadyExistsError("order_exists") from exc

    LOG.info(
        "Created Mozello order email=%s mz_handle=%s user_id=%s book_id=%s",
        normalized_email,
        handle_clean,
        order.calibre_user_id,
        order.calibre_book_id,
    )
    view = _order_to_view(order, book_info, user_info)
    return {"order": view.__dict__, "status": "created"}


def create_user_for_order(order_id: int) -> Dict[str, Any]:
    order = users_books_repo.get_order(order_id)
    if not order:
        raise OrderNotFoundError("order_missing")

    book_map = books_sync.lookup_books_by_handles({order.mz_handle.lower()}) if order.mz_handle else {}
    book_info = book_map.get(order.mz_handle.lower()) if order.mz_handle else None

    existing_user = lookup_user_by_email(order.email)
    if existing_user:
        if not order.calibre_user_id:
            users_books_repo.update_links(order.id, calibre_user_id=existing_user.get("id"))
            order.calibre_user_id = existing_user.get("id")
        view_existing = _order_to_view(order, book_info, existing_user)
        return {
            "order": view_existing.__dict__,
            "user": existing_user,
            "password": None,
            "status": "linked_existing",
        }

    try:
        user_info, password = create_user_for_email(order.email)
    except UserAlreadyExistsError as exc:
        refreshed = lookup_user_by_email(order.email)
        if refreshed:
            users_books_repo.update_links(order.id, calibre_user_id=refreshed.get("id"))
            order.calibre_user_id = refreshed.get("id")
            view_refreshed = _order_to_view(order, book_info, refreshed)
            return {
                "order": view_refreshed.__dict__,
                "user": refreshed,
                "password": None,
                "status": "linked_existing",
            }
        raise UserAlreadyExistsError("user_exists") from exc
    except CalibreUnavailableError as exc:
        raise CalibreUnavailableError("calibre_unavailable") from exc

    users_books_repo.update_links(order.id, calibre_user_id=user_info.get("id"))
    order.calibre_user_id = user_info.get("id")

    view = _order_to_view(order, book_info, user_info)
    return {"order": view.__dict__, "user": user_info, "password": password, "status": "created"}


def refresh_order(order_id: int) -> Dict[str, Any]:
    order = users_books_repo.get_order(order_id)
    if not order:
        raise OrderNotFoundError("order_missing")

    book_map = books_sync.lookup_books_by_handles({order.mz_handle.lower()}) if order.mz_handle else {}
    book_info = book_map.get(order.mz_handle.lower()) if order.mz_handle else None
    user_info = lookup_user_by_email(order.email)

    if book_info and order.calibre_book_id != book_info.get("book_id"):
        users_books_repo.update_links(order.id, calibre_book_id=book_info.get("book_id"))
        order.calibre_book_id = book_info.get("book_id")
    if user_info and order.calibre_user_id != user_info.get("id"):
        users_books_repo.update_links(order.id, calibre_user_id=user_info.get("id"))
        order.calibre_user_id = user_info.get("id")

    view = _order_to_view(order, book_info, user_info)
    return {"order": view.__dict__, "status": "refreshed"}


__all__ = [
    "list_orders",
    "create_order",
    "create_user_for_order",
    "refresh_order",
    "OrderValidationError",
    "OrderAlreadyExistsError",
    "OrderNotFoundError",
    "CalibreUnavailableError",
    "UserAlreadyExistsError",
]