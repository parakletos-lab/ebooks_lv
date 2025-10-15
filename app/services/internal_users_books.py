"""Legacy placeholder for removed users_books allow-list logic."""

from __future__ import annotations


def __getattr__(name):  # pragma: no cover - defensive path
    raise AttributeError(
        "users_books allow-list logic has been replaced by Mozello orders integration"
    )


__all__ = []
