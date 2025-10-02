"""Minimal constants used by integrated users_books admin routes.

Provides a thin indirection over upstream Calibre-Web constants so our
application layer doesn't import `cps.constants` in many places and we can
mock easily in tests.
"""
from __future__ import annotations

try:  # Upstream Calibre-Web constants
    from cps import constants as _cw_constants  # type: ignore
except Exception:  # pragma: no cover - startup fallback
    class _Fallback:  # type: ignore
        ROLE_ADMIN = 0
    _cw_constants = _Fallback()  # type: ignore

# Public re‑exports (add more if needed later)
ROLE_ADMIN = getattr(_cw_constants, "ROLE_ADMIN", 0)

__all__ = ["ROLE_ADMIN"]
