"""
routes_user.py

User-facing REST API routes for the users_books plugin.

Endpoints (mounted under /plugin/users_books):

  GET    /filters
      List the current user's allowed book IDs (ordered ascending).

  POST   /filters
      Body: { "book_id": <int> }
      Adds a single (user_id, book_id) mapping if not already present.
      Responses:
        200 { "status": "added" | "exists", "user_id": <int>, "book_id": <int> }

  DELETE /filters/<book_id>
      Removes a single mapping (if it exists).
      Responses:
        200 { "status": "deleted" | "not_found", "user_id": <int>, "book_id": <int> }

  POST   /filters/bulk
      Body: { "book_ids": [ <int>, ... ] }
      Adds multiple book IDs; ignores duplicates and existing mappings.
      Responses:
        200 {
          "requested": <int>,
          "added": <int>,
          "skipped_existing": <int>,
          "book_ids_added": [...],
          "book_ids_existing": [...]
        }

  PUT    /filters/upsert
      Body: { "book_ids": [ <int>, ... ] }
      Reconciles the user's allow-list to match exactly the provided set:
        - Inserts missing
        - Removes obsolete
      Responses:
        200 {
          "desired": <int>,
          "added": <int>,
          "removed": <int>,
          "final_total": <int>,
          "added_ids": [...],
          "removed_ids": [...]
        }

Common Error Responses:
  401 { "error": "Not authenticated" }
  400 { "error": "<message>" }

Implementation Notes:
  - All business logic delegated to services.*
  - Session / user identity retrieved via utils.get_current_user_id().
  - No direct DB access here to maintain layering discipline.
  - Input validation is intentionally strict to avoid silent coercions.

Extensibility:
  - Additional endpoints (e.g., pagination) can be added by extending list handler.
  - Tag-based filtering or metadata expansion would live in services first.

"""

from __future__ import annotations

from typing import Any, List, Dict

from flask import request, jsonify

from .. import services
from .. import utils


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _require_user_id():
    """
    Return current user_id or a tuple (response, status) if unauthenticated.

    Caller pattern:
        uid = _require_user_id()
        if isinstance(uid, tuple):
            return uid  # early exit with error response
    """
    uid = utils.get_current_user_id()
    if uid is None:
        return _json_error("Not authenticated", 401)
    return uid


def _coerce_int_list(raw) -> List[int]:
    """
    Safely coerce an incoming list-like payload to a list[int], dropping invalid entries.
    Raises ValueError if the result would be empty or the raw type is not acceptable.
    """
    if not isinstance(raw, (list, tuple)):
        raise ValueError("book_ids must be an array of integers")
    out = []
    for val in raw:
        if isinstance(val, bool):
            # Exclude booleans (they are ints subclassing in Python)
            continue
        try:
            iv = int(val)
        except (TypeError, ValueError):
            continue
        out.append(iv)
    if not out:
        raise ValueError("No valid integers found in book_ids")
    return out


# ---------------------------------------------------------------------------
# Route Registration
# ---------------------------------------------------------------------------

def register(bp):
    """
    Attach user-facing routes to the provided Blueprint.
    """

    @bp.route("/filters", methods=["GET"])
    def list_own_filters():
        uid = _require_user_id()
        if isinstance(uid, tuple):
            return uid
        ids = services.list_user_book_ids(uid, use_cache=True)
        return jsonify({
            "user_id": uid,
            "allowed_book_ids": ids,
            "count": len(ids),
        })

    @bp.route("/filters", methods=["POST"])
    def add_own_filter():
        uid = _require_user_id()
        if isinstance(uid, tuple):
            return uid

        data = request.get_json(silent=True) or {}
        book_id = data.get("book_id")
        if not isinstance(book_id, int):
            # Allow numeric strings but disallow bool
            if isinstance(book_id, str):
                try:
                    book_id = int(book_id)
                except ValueError:
                    return _json_error("Missing or invalid 'book_id' (integer required)")
            else:
                return _json_error("Missing or invalid 'book_id' (integer required)")

        created = services.add_user_book(uid, book_id)
        status = "added" if created else "exists"
        return jsonify({
            "status": status,
            "user_id": uid,
            "book_id": book_id,
        })

    @bp.route("/filters/<int:book_id>", methods=["DELETE"])
    def delete_own_filter(book_id: int):
        uid = _require_user_id()
        if isinstance(uid, tuple):
            return uid

        removed = services.remove_user_book(uid, book_id)
        status = "deleted" if removed else "not_found"
        return jsonify({
            "status": status,
            "user_id": uid,
            "book_id": book_id,
        })

    @bp.route("/filters/bulk", methods=["POST"])
    def bulk_add_filters():
        uid = _require_user_id()
        if isinstance(uid, tuple):
            return uid

        data = request.get_json(silent=True) or {}
        raw_ids = data.get("book_ids")
        try:
            ids = _coerce_int_list(raw_ids)
        except ValueError as exc:
            return _json_error(str(exc))

        summary = services.bulk_add_user_books(uid, ids)
        summary["user_id"] = uid
        return jsonify(summary)

    @bp.route("/filters/upsert", methods=["PUT"])
    def upsert_filters():
        uid = _require_user_id()
        if isinstance(uid, tuple):
            return uid

        data = request.get_json(silent=True) or {}
        raw_ids = data.get("book_ids")
        try:
            ids = _coerce_int_list(raw_ids)
        except ValueError as exc:
            return _json_error(str(exc))

        summary = services.upsert_user_books(uid, ids)
        summary["user_id"] = uid
        return jsonify(summary)


__all__ = ["register"]
