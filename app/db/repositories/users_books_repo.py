"""Repository helpers for Mozello order records (users_books DB)."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from app.db import plugin_session
from app.db.models import MozelloOrder


class OrderExistsError(Exception):
    """Raised when attempting to insert a duplicate (email, mz_handle) pair."""


def list_orders() -> List[MozelloOrder]:
    with plugin_session() as session:
        return (
            session.query(MozelloOrder)
            .order_by(MozelloOrder.created_at.desc(), MozelloOrder.id.desc())
            .all()
        )


def get_order(order_id: int) -> Optional[MozelloOrder]:
    with plugin_session() as session:
        return session.query(MozelloOrder).filter(MozelloOrder.id == order_id).one_or_none()


def get_order_by_email_handle(email: str, mz_handle: str) -> Optional[MozelloOrder]:
    """Fetch order by normalized email and Mozello handle."""
    with plugin_session() as session:
        return (
            session.query(MozelloOrder)
            .filter(MozelloOrder.email == email, MozelloOrder.mz_handle == mz_handle)
            .one_or_none()
        )


def create_order(
    email: str,
    mz_handle: str,
    calibre_user_id: Optional[int] = None,
    calibre_book_id: Optional[int] = None,
    mz_category_handle: Optional[str] = None,
    *,
    created_at: Optional[datetime] = None,
    imported_at: Optional[datetime] = None,
) -> MozelloOrder:
    payload = {
        "email": email,
        "mz_handle": mz_handle,
        "calibre_user_id": calibre_user_id,
        "calibre_book_id": calibre_book_id,
    }
    if mz_category_handle is not None:
        payload["mz_category_handle"] = (mz_category_handle or "").strip() or None
    if created_at is not None:
        payload["created_at"] = created_at
    if imported_at is not None:
        payload["updated_at"] = imported_at
    order = MozelloOrder(**payload)
    try:
        with plugin_session() as session:
            session.add(order)
    except IntegrityError as exc:
        raise OrderExistsError("Order already exists for email/handle") from exc
    return order


def update_links(
    order_id: int,
    calibre_user_id: Optional[int] = None,
    calibre_book_id: Optional[int] = None,
) -> Optional[MozelloOrder]:
    with plugin_session() as session:
        order = session.query(MozelloOrder).filter(MozelloOrder.id == order_id).one_or_none()
        if not order:
            return None
        if calibre_user_id is not None:
            order.calibre_user_id = calibre_user_id
        if calibre_book_id is not None:
            order.calibre_book_id = calibre_book_id
        return order


def bulk_update_links(updates: Iterable[tuple[int, Optional[int], Optional[int]]]) -> None:
    updates_list = list(updates)
    if not updates_list:
        return
    with plugin_session() as session:
        for order_id, user_id, book_id in updates_list:
            order = session.query(MozelloOrder).filter(MozelloOrder.id == order_id).one_or_none()
            if not order:
                continue
            if user_id is not None:
                order.calibre_user_id = user_id
            if book_id is not None:
                order.calibre_book_id = book_id


def mark_imported(
    email: str,
    mz_handle: str,
    imported_at: datetime,
    *,
    calibre_user_id: Optional[int] = None,
    calibre_book_id: Optional[int] = None,
    mz_category_handle: Optional[str] = None,
) -> Optional[MozelloOrder]:
    with plugin_session() as session:
        order = (
            session.query(MozelloOrder)
            .filter(MozelloOrder.email == email, MozelloOrder.mz_handle == mz_handle)
            .one_or_none()
        )
        if not order:
            return None
        order.updated_at = imported_at
        if calibre_user_id is not None and not order.calibre_user_id:
            order.calibre_user_id = calibre_user_id
        if calibre_book_id is not None and not order.calibre_book_id:
            order.calibre_book_id = calibre_book_id
        if mz_category_handle is not None:
            cleaned = (mz_category_handle or "").strip() or None
            if order.mz_category_handle != cleaned:
                order.mz_category_handle = cleaned
        return order


def delete_order(order_id: int) -> bool:
    with plugin_session() as session:
        order = session.query(MozelloOrder).filter(MozelloOrder.id == order_id).one_or_none()
        if not order:
            return False
        session.delete(order)
        return True


__all__ = [
    "OrderExistsError",
    "list_orders",
    "get_order",
    "get_order_by_email_handle",
    "create_order",
    "update_links",
    "bulk_update_links",
    "mark_imported",
    "delete_order",
    "update_category_handle_for_handle",
    "get_category_handle_for_handle",
    "list_orders_for_user",
]


def update_category_handle_for_handle(mz_handle: str, mz_category_handle: Optional[str]) -> int:
    cleaned_handle = (mz_handle or "").strip()
    if not cleaned_handle:
        return 0
    cleaned_category = (mz_category_handle or "").strip() or None
    updated = 0
    with plugin_session() as session:
        rows = (
            session.query(MozelloOrder)
            .filter(MozelloOrder.mz_handle == cleaned_handle)
            .all()
        )
        for row in rows:
            if row.mz_category_handle != cleaned_category:
                row.mz_category_handle = cleaned_category
                updated += 1
    return updated


def get_category_handle_for_handle(mz_handle: str) -> Optional[str]:
    cleaned_handle = (mz_handle or "").strip()
    if not cleaned_handle:
        return None
    with plugin_session() as session:
        order = (
            session.query(MozelloOrder)
            .filter(
                MozelloOrder.mz_handle == cleaned_handle,
                MozelloOrder.mz_category_handle.isnot(None),
                MozelloOrder.mz_category_handle != "",
            )
            .order_by(MozelloOrder.updated_at.desc(), MozelloOrder.id.desc())
            .first()
        )
        if not order:
            return None
        value = (order.mz_category_handle or "").strip()
        return value or None


def list_orders_for_user(
    *,
    calibre_user_id: Optional[int] = None,
    email: Optional[str] = None,
) -> List[MozelloOrder]:
    """Return all Mozello orders linked to the provided user identity."""
    filters = []
    if calibre_user_id is not None:
        filters.append(MozelloOrder.calibre_user_id == calibre_user_id)
    if email:
        filters.append(MozelloOrder.email == email)
    if not filters:
        return []
    with plugin_session() as session:
        query = session.query(MozelloOrder).filter(or_(*filters))
        return query.all()
