"""
models.py

SQLAlchemy ORM models for the users_books plugin.

Current Scope:
  - UserFilter: per-user allow-list mapping of (user_id, book_id)

Design Goals:
  - Keep models isolated from engine/session setup (handled in db.py).
  - Provide explicit uniqueness + composite index for efficient lookups
    and to prevent duplicate mappings.
  - Keep a minimal surface area so future migrations (additional tables,
    audit logs, group-based entitlements) can be added cleanly.

Table: users_books
  Columns:
    id        INTEGER PRIMARY KEY AUTOINCREMENT
    user_id   INTEGER NOT NULL (indexed)
    book_id   INTEGER NOT NULL (indexed)
  Constraints:
    UNIQUE(user_id, book_id)  -> uq_users_books_user_book
    INDEX(user_id, book_id)   -> ix_users_books_user_book
"""

from __future__ import annotations

from sqlalchemy.orm import declarative_base
from sqlalchemy import (
    Column,
    Integer,
    UniqueConstraint,
    Index,
)

Base = declarative_base()


class UserFilter(Base):
    """
    Mapping row granting a single user visibility to a specific book.

    Rationale:
      - Simplicity: an allow-list only (no deny-list logic yet).
      - Extensible: can later introduce group tables or denormalized
        aggregates if performance demands it.

    Important:
      - Do NOT add foreign key constraints here unless you are certain
        the Calibre-Web schema and plugin lifecycle will align; keeping
        this table loosely coupled (no FK) reduces upgrade friction.
    """
    __tablename__ = "users_books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)

    __table_args__ = (
        # Prevent duplicate mappings.
        UniqueConstraint("user_id", "book_id", name="uq_users_books_user_book"),
        # Composite index (helpful for combined lookups or future range scans).
        Index("ix_users_books_user_book", "user_id", "book_id"),
    )

    def as_dict(self) -> dict:
        """Return a simple serializable representation."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "book_id": self.book_id,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<UserFilter id={self.id} user_id={self.user_id} book_id={self.book_id}>"


# Public export surface
__all__ = [
    "Base",
    "UserFilter",
]
