
"""
filter_hook.py

SQLAlchemy query filtering hook for the users_books plugin.

Purpose
-------
Transparently constrains any SELECT statement that targets the Calibre-Web
Books table so that non-admin users only see rows (books) they are explicitly
allowed to view (as defined in the users_books table).

The hook attaches a `before_compile` listener to SQLAlchemy's Select object
(retval=True) and conditionally adds a `Books.id IN (<allowed_ids>)` predicate.

Key Behaviors
-------------
1. Skips filtering when:
   - Not inside a Flask request context.
   - User is not authenticated (no user_id in session).
   - User is an admin.
   - The statement does not involve the Books table.
   - Allowed ID list is empty and config.enforce_empty_behaviour() is False.
   - Allowed ID list length exceeds configured max_ids_in_clause() (fails open with warning).

2. Empty Allow-List Modes:
   - enforce_empty_behaviour() == True  => inject a FALSE predicate (return no rows)
   - enforce_empty_behaviour() == False => do not modify the statement (lenient)

3. Idempotence:
   - The listener only modifies a statement once by tagging it with a private
     compilation option.

4. Performance:
   - Uses per-request cached list of allowed IDs (leveraging services.list_user_book_ids).
   - If the allowed list is large and near parameter limits, consider migrating
     to a temp table strategy in the future.

Environment / Config (via config module)
---------------------------------------
USERS_BOOKS_ENFORCE_EMPTY        -> enforce_empty_behaviour()
USERS_BOOKS_MAX_IDS_IN_CLAUSE    -> max_ids_in_clause()

Dependencies
------------
- utils.get_current_user_id, utils.is_admin_user
- services.list_user_book_ids
- config.enforce_empty_behaviour / config.max_ids_in_clause
- Attempted import of `Books` from `cps.models`

Extensibility
-------------
- Add deny-list logic by extending predicate construction.
- Add advanced heuristics in `_should_filter_select` to skip certain queries.
- Provide alternate strategies when ID list exceeds threshold (e.g., join with
  a virtual table or a temporary table).

NOTE
----
The hook intentionally does not inspect or rewrite complex joins beyond checking
that Books is part of the FROM set. For advanced scenarios, add extra guards or
predicate pattern checks.

"""

from __future__ import annotations

from typing import Optional, Sequence, Any

from sqlalchemy import event
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import ClauseElement
from flask import has_request_context

from .logging_setup import get_logger
from . import config
from . import utils
from . import services

LOG = get_logger()

# Tag key to avoid double modification
_ALREADY_FILTERED_OPTION = "_users_books_already_filtered"

# Deferred / lazy import of Books; set after first successful resolution.
_BooksModel: Any | None = None
_TRIED_IMPORT = False


def _import_books_model() -> Optional[Any]:
    """Resolve the Calibre-Web Books model.

    Older assumptions tried cps.models.Books, but the actual model lives
    in cps.db. We: (1) try cached value, (2) attempt cps.db.Books, (3) then
    cps.models.Books (for forward compatibility). We only mark _TRIED_IMPORT
    after attempts to avoid permanently failing due to an initial bad path.
    """
    global _BooksModel, _TRIED_IMPORT
    if _BooksModel is not None:
        return _BooksModel
    if _TRIED_IMPORT:
        return _BooksModel
    # Attempt canonical location first
    for mod_path in ("cps.db", "cps.models"):
        try:
            module = __import__(mod_path, fromlist=["Books"])  # type: ignore
            books = getattr(module, "Books", None)
            if books is not None and hasattr(books, "__table__"):
                _BooksModel = books
                LOG.debug("users_books: Resolved Books model from %s", mod_path)
                break
        except Exception as exc:  # pragma: no cover
            LOG.debug("users_books: Books import attempt failed from %s: %s", mod_path, exc)
    _TRIED_IMPORT = True
    return _BooksModel


def _select_involves_books(stmt: Select) -> bool:
    """
    Return True if the Select's FROMs include the Books table.
    """
    books = _import_books_model()
    if books is None or not hasattr(books, "__table__"):
        return False

    try:
        for from_clause in stmt.get_final_froms():
            if from_clause is books.__table__:
                return True
    except Exception:  # pragma: no cover
        return False
    return False


def _already_filtered(stmt: Select) -> bool:
    """
    Check if we have already processed this statement.
    We use compilation options as a tagging mechanism.
    """
    return bool(getattr(stmt, "_compiler_options", {}).get(_ALREADY_FILTERED_OPTION))


def _mark_filtered(stmt: Select) -> Select:
    """
    Return a copy of the Select with an option flag marking it as processed.
    """
    return stmt.with_compile_options(**{_ALREADY_FILTERED_OPTION: True})


def _inject_false(stmt: Select) -> Select:
    """
    Constrain statement to return no rows (1=0 / FALSE).
    """
    from sqlalchemy import literal
    return stmt.where(literal(False))


def _inject_id_filter(stmt: Select, ids: Sequence[int]) -> Select:
    """
    Constrain statement with Books.id IN (ids).
    """
    books = _import_books_model()
    if not books:
        return stmt
    return stmt.where(books.id.in_(ids))  # type: ignore[attr-defined]


def _build_filtered_statement(stmt: Select, user_id: int, allowed_ids: list[int]) -> Select:
    """
    Decide how to modify the statement based on allowed IDs and config.
    """
    enforce_empty = config.enforce_empty_behaviour()
    if not allowed_ids:
        if enforce_empty:
            return _inject_false(stmt)
        # Lenient mode: leave statement unchanged
        return stmt

    max_ids = config.max_ids_in_clause()
    if len(allowed_ids) > max_ids:
        LOG.warning(
            "Allowed book ID list size %d exceeds max_ids_in_clause=%d; skipping filter for user_id=%s",
            len(allowed_ids),
            max_ids,
            user_id,
        )
        return stmt
    return _inject_id_filter(stmt, allowed_ids)


def _before_compile_listener(stmt: ClauseElement) -> ClauseElement:
    """
    Primary listener for SQLAlchemy before_compile events.

    Only processes instances of Select and returns a (possibly) modified copy.
    """
    # Fast escapes
    if not isinstance(stmt, Select):
        return stmt
    if _already_filtered(stmt):
        return stmt
    if not has_request_context():
        return stmt

    user_id = utils.get_current_user_id()
    if user_id is None or utils.is_admin_user():
        return stmt
    if not _select_involves_books(stmt):
        return stmt

    # Obtain allowed IDs (may use per-request cache via services)
    try:
        allowed_ids = services.list_user_book_ids(user_id, use_cache=True)
    except Exception as exc:  # pragma: no cover - defensive
        LOG.error("Error retrieving allowed IDs for user_id=%s: %s", user_id, exc, exc_info=True)
        return stmt

    LOG.debug(
        "users_books: considering filter user_id=%s allowed_count=%d stmt=%s",
        user_id, len(allowed_ids), getattr(stmt, 'select_from', None)
    )
    new_stmt = _build_filtered_statement(stmt, user_id, allowed_ids)
    if new_stmt is not stmt:
        LOG.debug("users_books: filter applied user_id=%s ids=%s", user_id, allowed_ids)
    return _mark_filtered(new_stmt)


def attach_filter_hook() -> None:
    """
    Attach the filtering hook exactly once.

    Uses a private attribute on the function to guard against
    multiple attachments (idempotent).
    """
    if getattr(attach_filter_hook, "_attached", False):
        return

    try:
        # Attempt modern SQLAlchemy 2.x style event on Select
        event.listen(Select, "before_compile", _before_compile_listener, retval=True)
        LOG.info("users_books filter hook attached to SQLAlchemy Select (before_compile).")
        setattr(attach_filter_hook, "_attached", True)
        return
    except Exception as exc:
        LOG.warning("Select-level before_compile not supported (%s); attempting Query fallback.", exc)

    # Fallback: older SQLAlchemy versions may only support Query before_compile
    try:
        from sqlalchemy.orm import Query  # type: ignore
        event.listen(Query, "before_compile", _before_compile_listener, retval=True)
        LOG.info("users_books filter hook attached to SQLAlchemy Query (fallback).")
        setattr(attach_filter_hook, "_attached", True)
    except Exception as exc:  # pragma: no cover - defensive
        LOG.error("Failed to attach users_books filter hook (Select + Query attempts failed): %s", exc)


__all__ = [
    "attach_filter_hook",
]
