"""
routes_webhook.py

Purchase webhook integration for the users_books plugin.

Endpoint (mounted under /plugin/users_books):

  POST /plugin/users_books/webhook/purchase
    Headers:
      Content-Type: application/json
      X-API-Key: <USERS_BOOKS_WEBHOOK_API_KEY>
    Body (JSON):
      {
        "email": "buyer@example.com",
        "book_id": 123
      }

Purpose:
  - Grants a user access to (book_id) by resolving their email in the native
    Calibre-Web user database (no email data persisted in plugin DB).
  - If the user does not exist yet, returns status=user_not_found (404) so the
    caller can retry later once the account is created.

Responses:
  200 {
        "status": "created" | "exists",
        "user_id": <int>,
        "book_id": <int>
      }
  404 {
        "status": "user_not_found",
        "email": "<normalized email>",
        "book_id": <int>
      }
  400 { "error": "<message>" }
  401 { "error": "Unauthorized" }  (missing / bad API key)
  403 { "error": "Webhook disabled (API key not configured)" }

Security:
  - Simple API key header. Keep USERS_BOOKS_WEBHOOK_API_KEY secret.
  - Optionally front with reverse proxy IP allow-list or HMAC signature.

Idempotence:
  - Achieved by checking if (user_id, book_id) mapping already exists
    before insertion (services.add_user_book returns False if it exists).

Extensibility Ideas:
  - Batch endpoint: /webhook/purchase/bulk
  - Optional HMAC: X-Signature header
  - Include order_id / transaction_id for audit logging (if you add an audit table)
  - Retry hints (e.g., "retry_after") when user not found
"""

from __future__ import annotations

from flask import request, jsonify

from .. import config, services, utils
from ..logging_setup import get_logger

LOG = get_logger()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def _normalize_and_validate_payload():
    """
    Extract and validate webhook JSON payload.

    Returns:
        (email: str, book_id: int) on success
        (response, status) tuple on failure (caller should return it)
    """
    if not request.is_json:
        return _json_error("Expected JSON body", 400)
    data = request.get_json(silent=True) or {}

    raw_email = data.get("email")
    book_id = data.get("book_id")

    email = utils.normalize_email(raw_email)
    if not email:
        return _json_error("Invalid or missing 'email'", 400)

    if isinstance(book_id, bool):  # exclude bool (bool is subclass of int)
        return _json_error("Invalid 'book_id' (boolean not allowed)", 400)

    if not isinstance(book_id, int):
        # Allow numeric string
        if isinstance(book_id, str):
            try:
                book_id = int(book_id)
            except ValueError:
                return _json_error("Invalid 'book_id' (must be integer)", 400)
        else:
            return _json_error("Invalid or missing 'book_id'", 400)

    if book_id < 0:
        return _json_error("'book_id' must be non-negative", 400)

    return email, book_id


def _authorize_webhook():
    """
    Return True if authorized, else (response, status).
    """
    api_key = config.webhook_api_key()
    if not api_key:
        return _json_error("Webhook disabled (API key not configured)", 403)

    supplied = request.headers.get("X-API-Key")
    if supplied != api_key:
        return _json_error("Unauthorized", 401)
    return True


# ---------------------------------------------------------------------------
# Route Registration
# ---------------------------------------------------------------------------

def register(bp):
    """
    Register webhook purchase route on the provided blueprint.
    """

    @bp.route("/webhook/purchase", methods=["POST"])
    def webhook_purchase():
        # Auth
        auth = _authorize_webhook()
        if auth is not True:
            return auth  # (response, status)

        # Payload
        parsed = _normalize_and_validate_payload()
        if isinstance(parsed, tuple) and len(parsed) == 2 and isinstance(parsed[0], str):
            # Success path: (email, book_id)
            email, book_id = parsed  # type: ignore
        else:
            # Error path: parsed is already (response, status)
            return parsed  # type: ignore

        # Resolve user
        user_id = utils.resolve_user_id_by_email(email)
        if user_id is None:
            return jsonify({
                "status": "user_not_found",
                "email": email,
                "book_id": book_id,
            }), 404

        # Add mapping if needed
        created = services.add_user_book(user_id, book_id)
        status = "created" if created else "exists"
        LOG.info(
            "webhook_purchase: email=%s user_id=%s book_id=%s status=%s",
            email, user_id, book_id, status
        )
        return jsonify({
            "status": status,
            "user_id": user_id,
            "book_id": book_id,
        })


__all__ = ["register"]
