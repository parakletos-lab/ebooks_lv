"""Mozello orders service orchestration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, time
from typing import Any, Dict, List, Optional, Set
import json

from app.db.models import MozelloOrder
from app.db.repositories import users_books_repo
from app.db.repositories.users_books_repo import OrderExistsError as RepoOrderExistsError
from app.services import books_sync, mozello_service, password_reset_service, email_delivery
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


def create_user_for_order(
    order_id: int,
    *,
    preferred_username: Optional[str] = None,
    preferred_language: Optional[str] = None,
) -> Dict[str, Any]:
    order = users_books_repo.get_order(order_id)
    if not order:
        raise OrderNotFoundError("order_missing")

    book_map = books_sync.lookup_books_by_handles({order.mz_handle.lower()}) if order.mz_handle else {}
    book_info = book_map.get(order.mz_handle.lower()) if order.mz_handle else None
    language_hint = preferred_language or (book_info.get("language_code") if book_info else None)

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
        user_info, password = create_user_for_email(
            order.email,
            preferred_username=preferred_username,
            preferred_language=language_hint,
        )
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
                users_books_repo.mark_imported(
                    email_norm,
                    handle_raw,
                    imported_at_ts,
                    calibre_user_id=calibre_user_id,
                    calibre_book_id=calibre_book_id,
                )
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


def process_webhook_order(order_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Persist a paid Mozello order delivered via webhook and ensure Calibre user.

    Returns summary containing per-handle outcomes and user creation/link status.
    Raises OrderValidationError for invalid payloads and propagates CalibreUnavailableError
    when Calibre is unreachable.
    """
    if not isinstance(order_payload, dict):
        raise OrderValidationError("invalid_payload")

    payment_status = str(order_payload.get("payment_status") or "").strip().lower()
    if payment_status != "paid":
        raise OrderValidationError("payment_not_paid")

    email_norm = normalize_email(order_payload.get("email"))
    if not email_norm:
        raise OrderValidationError("email_required")

    cart_raw = order_payload.get("cart") or []
    if not isinstance(cart_raw, list) or not cart_raw:
        raise OrderValidationError("cart_required")

    seen_handles: Set[str] = set()
    handles: List[str] = []
    for item in cart_raw:
        if not isinstance(item, dict):
            continue
        handle_raw = (item.get("product_handle") or "").strip()
        if not handle_raw:
            continue
        handle_key = handle_raw.lower()
        if handle_key in seen_handles:
            continue
        seen_handles.add(handle_key)
        handles.append(handle_raw)

    if not handles:
        raise OrderValidationError("handles_missing")

    moz_created_at = _parse_mozello_timestamp(order_payload.get("created_at"))
    imported_at = datetime.utcnow()

    book_map = books_sync.lookup_books_by_handles(seen_handles) if seen_handles else {}
    existing_user = lookup_user_by_email(email_norm)
    moz_customer_name = (order_payload.get("name") or "").strip() or None

    summary: Dict[str, Any] = {
        "email": email_norm,
        "mozello_order_id": order_payload.get("order_id"),
        "orders_total": len(handles),
        "orders_created": 0,
        "orders_existing": 0,
        "user_created": 0,
        "user_linked": 0,
        "books_included": 0,
        "email_queued": False,
        "email_error": None,
        "email_language": None,
        "initial_token_issued": False,
        "initial_token_error": None,
        "orders": [],
        "errors": [],
    }
    books_for_email: List[email_delivery.BookDeliveryItem] = []
    book_ids_for_token: List[int] = []
    book_ids_seen: Set[int] = set()
    initial_password: Optional[str] = None

    for handle in handles:
        handle_key = handle.lower()
        book_info = book_map.get(handle_key)
        calibre_user_id = existing_user.get("id") if existing_user else None
        calibre_book_id = book_info.get("book_id") if book_info else None
        language_hint = book_info.get("language_code") if book_info else None
        book_id_int: Optional[int] = None
        if calibre_book_id is not None:
            try:
                book_id_int = int(calibre_book_id)
            except (TypeError, ValueError):
                book_id_int = None
        if book_id_int:
            books_for_email.append(
                email_delivery.BookDeliveryItem(
                    book_id=book_id_int,
                    title=book_info.get("title") if book_info and book_info.get("title") else handle,
                    language_code=book_info.get("language_code") if book_info else None,
                )
            )
            if book_id_int not in book_ids_seen:
                book_ids_seen.add(book_id_int)
                book_ids_for_token.append(book_id_int)
        created = False
        order_obj: Optional[MozelloOrder]
        try:
            order_obj = users_books_repo.create_order(
                email_norm,
                handle,
                calibre_user_id=calibre_user_id,
                calibre_book_id=calibre_book_id,
                created_at=moz_created_at,
                imported_at=imported_at,
            )
            created = True
            summary["orders_created"] += 1
        except RepoOrderExistsError:
            summary["orders_existing"] += 1
            order_obj = users_books_repo.mark_imported(
                email_norm,
                handle,
                imported_at,
                calibre_user_id=calibre_user_id,
                calibre_book_id=calibre_book_id,
            )
            if not order_obj:
                order_obj = users_books_repo.get_order_by_email_handle(email_norm, handle)

        if not order_obj:
            LOG.warning("Webhook Mozello order missing after persistence email=%s handle=%s", email_norm, handle)
            summary["errors"].append({"handle": handle, "error": "order_missing"})
            summary["orders"].append({
                "order_id": None,
                "mz_handle": handle,
                "status": "error",
                "user_status": None,
            })
            continue

        user_status = "already_linked" if order_obj.calibre_user_id else None

        if not order_obj.calibre_user_id:
            try:
                ensure_resp = create_user_for_order(
                    order_obj.id,
                    preferred_username=moz_customer_name,
                    preferred_language=language_hint,
                )
                ensure_status = ensure_resp.get("status") or "linked_existing"
                user_status = ensure_status
                user_obj = ensure_resp.get("user")
                if user_obj:
                    existing_user = user_obj
                else:
                    refreshed = lookup_user_by_email(email_norm)
                    if refreshed:
                        existing_user = refreshed
                if ensure_status == "created":
                    summary["user_created"] += 1
                    if not initial_password:
                        initial_password = ensure_resp.get("password")
                else:
                    summary["user_linked"] += 1
            except UserAlreadyExistsError:
                refreshed_user = lookup_user_by_email(email_norm)
                if refreshed_user:
                    existing_user = refreshed_user
                    summary["user_linked"] += 1
                    user_status = "linked_existing"
                else:
                    summary["errors"].append({
                        "handle": handle,
                        "error": "user_exists_without_lookup",
                    })
                    user_status = "user_error"
            except CalibreUnavailableError as exc:
                LOG.error(
                    "Mozello webhook Calibre unavailable email=%s handle=%s error=%s",
                    email_norm,
                    handle,
                    exc,
                )
                raise
            except Exception as exc:  # pragma: no cover - defensive logging
                LOG.warning(
                    "Mozello webhook user creation failed email=%s handle=%s error=%s",
                    email_norm,
                    handle,
                    exc,
                )
                summary["errors"].append({"handle": handle, "error": str(exc)})
                user_status = "user_error"
        else:
            summary["user_linked"] += 1

        summary["orders"].append({
            "order_id": order_obj.id,
            "mz_handle": handle,
            "status": "created" if created else "existing",
            "user_status": user_status,
        })

    summary["books_included"] = len(books_for_email)
    auth_token: Optional[str] = None
    if initial_password:
        try:
            auth_token = password_reset_service.issue_initial_token(
                email=email_norm,
                temp_password=initial_password,
                book_ids=book_ids_for_token,
            )
            summary["initial_token_issued"] = True
        except password_reset_service.PasswordResetError as exc:
            summary["initial_token_error"] = str(exc)
            summary["errors"].append({"handle": None, "error": f"initial_token_failed:{exc}"})

    if existing_user and books_for_email:
        try:
            email_result = email_delivery.send_book_purchase_email(
                recipient_email=email_norm,
                user_name=existing_user.get("name") or existing_user.get("email") or email_norm,
                books=books_for_email,
                shop_url=mozello_service.get_store_url(
                    existing_user.get("locale") if isinstance(existing_user, dict) else None
                ),
                auth_token=auth_token,
                preferred_language=existing_user.get("locale") if isinstance(existing_user, dict) else None,
            )
            summary["email_queued"] = True
            summary["email_language"] = email_result.get("language")
        except email_delivery.EmailDeliveryError as exc:
            summary["email_error"] = str(exc)
            summary["errors"].append({"handle": None, "error": f"email_delivery:{exc}"})
    elif not books_for_email:
        LOG.debug("Mozello purchase email skipped email=%s reason=no_books", email_norm)
    else:
        LOG.debug("Mozello purchase email skipped email=%s reason=user_missing", email_norm)

    return {"status": "ok", "summary": summary}

__all__ = [
    "list_orders",
    "create_order",
    "create_user_for_order",
    "refresh_order",
    "delete_order",
    "import_paid_orders",
    "process_webhook_order",
    "OrderValidationError",
    "OrderAlreadyExistsError",
    "OrderNotFoundError",
    "OrderImportError",
    "CalibreUnavailableError",
    "UserAlreadyExistsError",
]
