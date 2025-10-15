"""Legacy compatibility shim forwarding to new orders service.

Existing imports that still reference this module will now interact with the
Mozello orders service. Remove once callers migrate to orders_service.
"""
from __future__ import annotations

from app.services.orders_service import (
    create_order,
    create_user_for_order,
    list_orders,
    refresh_order,
)

__all__ = [
    "list_orders",
    "create_order",
    "create_user_for_order",
    "refresh_order",
]
