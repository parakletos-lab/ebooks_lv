"""Legacy placeholder for retired users_books admin routes.

The Mozello orders implementation replaces this blueprint. Importing this
module is considered an error to surface any lingering references.
"""
from __future__ import annotations


def register_blueprint(app):  # pragma: no cover - defensive guard
    raise RuntimeError("users_books admin routes have been removed; use orders admin")

__all__ = ["register_blueprint"]
