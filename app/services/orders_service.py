"""Mozello orders service orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, time
from typing import Any, Dict, List, Optional, Set
import json

from app.db.models import MozelloOrder
from app.db.repositories import users_books_repo
from app.db.repositories.users_books_repo import OrderExistsError as RepoOrderExistsError
from app.services import books_sync, mozello_service
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


class OrderImportError(RuntimeError):
    """Raised when Mozello import fails."""


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
    imported_at: Optional[str]


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
        imported_at=order.updated_at.isoformat() if order.updated_at else None,
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
    imported_at = datetime.utcnow()

    try:
        order = users_books_repo.create_order(
            normalized_email,
            handle_clean,
            calibre_user_id=user_info.get("id") if user_info else None,
            calibre_book_id=book_info.get("book_id") if book_info else None,
            imported_at=imported_at,
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


def delete_order(order_id: int) -> Dict[str, Any]:
    removed = users_books_repo.delete_order(order_id)
    if not removed:
        raise OrderNotFoundError("order_missing")
    return {"status": "deleted"}


def _parse_mozello_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
    )
    for fmt in formats:
        try:
            return datetime.strptime(candidate, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _parse_date_input(raw: Optional[str]) -> Optional[datetime]:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise OrderValidationError("invalid_date") from exc
    return parsed


def import_paid_orders(
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    start_parsed = _parse_date_input(start_date)
    end_parsed = _parse_date_input(end_date)
    if start_parsed and end_parsed and end_parsed < start_parsed:
        raise OrderValidationError("invalid_date_range")
    start_dt = datetime.combine(start_parsed, time.min) if start_parsed else None
    end_dt = datetime.combine(end_parsed, time(23, 59, 59)) if end_parsed else None

    ok, payload = mozello_service.fetch_paid_orders(start_date=start_dt, end_date=end_dt)
    if not ok:
        # Surface full payload for diagnostics (will be returned as error message)
        try:
            details = json.dumps(payload)
        except Exception:
            details = str(payload)
        LOG.warning("Mozello fetch_paid_orders failed: %s", details)
        raise OrderImportError(details)

    raw_orders = payload.get("orders") if isinstance(payload, dict) else None
    if not isinstance(raw_orders, list):
        raise OrderImportError("invalid_payload")

    handles: Set[str] = set()
    emails: Set[str] = set()
    for item in raw_orders:
        if not isinstance(item, dict):
            continue
        email_norm = normalize_email(item.get("email"))
        if email_norm:
            emails.add(email_norm)
        for cart_item in item.get("cart") or []:
            handle = (cart_item.get("product_handle") or "").strip()
            if handle:
                handles.add(handle.lower())

    book_map = books_sync.lookup_books_by_handles(handles) if handles else {}
    user_map = lookup_users_by_emails(emails) if emails else {}

    imported_at_ts = datetime.utcnow()

    summary = {
        "fetched": len(raw_orders),
        "created": 0,
        "skipped": 0,
        "skipped_existing": 0,
        "skipped_filtered": 0,
        "errors": [],
    }
    created_ids: List[int] = []

    existing_pairs: Set[tuple[str, str]] = set()
    for record in users_books_repo.list_orders():
        email_key = normalize_email(record.email)
        handle_key = (record.mz_handle or "").strip().lower()
        if not email_key or not handle_key:
            continue
        existing_pairs.add((email_key, handle_key))

    for item in raw_orders:
        if not isinstance(item, dict):
            summary["skipped_filtered"] += 1
            continue
        email_norm = normalize_email(item.get("email"))
        if not email_norm:
            summary["skipped_filtered"] += 1
            continue
        moz_created_at = _parse_mozello_timestamp(item.get("created_at"))
        if start_dt and moz_created_at and moz_created_at < start_dt:
            summary["skipped_filtered"] += 1
            continue
        if end_dt and moz_created_at and moz_created_at > end_dt:
            summary["skipped_filtered"] += 1
            continue
        user_info = user_map.get(email_norm)
        cart = item.get("cart") or []
        if not cart:
            summary["skipped_filtered"] += 1
            continue
        seen_handles: Set[str] = set()
        for cart_item in cart:
            handle_raw = (cart_item.get("product_handle") or "").strip()
            if not handle_raw:
                summary["skipped_filtered"] += 1
                continue
            handle_key = handle_raw.lower()
            if handle_key in seen_handles:
                continue
            seen_handles.add(handle_key)
            pair_key = (email_norm, handle_key)
            if pair_key in existing_pairs:
                summary["skipped_existing"] += 1
                continue
            book_info = book_map.get(handle_key)
            calibre_user_id = user_info.get("id") if user_info else None
            calibre_book_id = book_info.get("book_id") if book_info else None
            try:
                order = users_books_repo.create_order(
                    email_norm,
                    handle_raw,
                    calibre_user_id=calibre_user_id,
                    calibre_book_id=calibre_book_id,
                    created_at=moz_created_at,
                    imported_at=imported_at_ts,
                )
                summary["created"] += 1
                created_ids.append(order.id)
                existing_pairs.add(pair_key)
            except RepoOrderExistsError:
                summary["skipped_existing"] += 1
            except Exception as exc:  # pragma: no cover - defensive
                summary["errors"].append({
                    "email": email_norm,
                    "handle": handle_raw,
                    "error": str(exc),
                })
                LOG.warning("Mozello import failed email=%s handle=%s error=%s", email_norm, handle_raw, exc)

    summary["skipped"] = summary["skipped_existing"] + summary["skipped_filtered"]
    summary["created_ids"] = created_ids
    return {"status": "ok", "summary": summary}


__all__ = [
    "list_orders",
    "create_order",
    "create_user_for_order",
    "refresh_order",
    "delete_order",
    "import_paid_orders",
    "OrderValidationError",
    "OrderAlreadyExistsError",
    "OrderNotFoundError",
    "OrderImportError",
    "CalibreUnavailableError",
    "UserAlreadyExistsError",
]
