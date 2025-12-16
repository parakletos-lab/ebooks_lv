from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional

from flask import g

try:  # pragma: no cover - optional in tests
    from flask_babel import get_locale  # type: ignore
except Exception:  # pragma: no cover
    get_locale = None  # type: ignore


def _normalize_lang(value: Any) -> str:
    if value is None:
        return "en"
    text = str(value)
    if not text:
        return "en"
    lowered = text.replace("-", "_").lower()
    return lowered.split("_")[0] or "en"


def _format_number(value: Decimal, decimal_sep: str, thousands_sep: str) -> str:
    sign = "-" if value.is_signed() else ""
    q = value.copy_abs()
    as_str = f"{q:.2f}"
    whole, frac = as_str.split(".")
    # group thousands
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    grouped = thousands_sep.join(reversed(groups)) if groups else "0"
    return f"{sign}{grouped}{decimal_sep}{frac}"


def format_eur(value: Any) -> str:
    """Format a numeric value as EUR for the current UI language.

    - Prefixes with the euro sign (no space): "€6,50".
    - Uses comma decimal separator for LV/RU, dot for EN.
    """
    if value is None or value == "":
        return ""
    try:
        dec = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return ""

    # The storefront uses EUR and we want a consistent EU-style rendering:
    # comma decimals, euro sign before the amount.
    formatted = _format_number(dec, decimal_sep=",", thousands_sep=" ")
    return f"€{formatted}"


def register_currency_filters(app: Any) -> None:
    """Register custom Jinja filters used by injected template patches."""
    env = getattr(app, "jinja_env", None)
    if not env:
        return
    filters = getattr(env, "filters", None)
    if not isinstance(filters, dict):
        return
    if "format_eur" not in filters:
        filters["format_eur"] = format_eur


__all__ = ["format_eur", "register_currency_filters"]
