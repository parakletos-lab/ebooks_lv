"""users_books ORM models (migrated from legacy plugin).

Original source: plugins.users_books.models
Purpose: define per-user allow list mapping table.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, UniqueConstraint, Index, String, Text, DateTime
import json, datetime

Base = declarative_base()


class UserFilter(Base):
    __tablename__ = "users_books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    book_id = Column(Integer, nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_users_books_user_book"),
        Index("ix_users_books_user_book", "user_id", "book_id"),
    )

    def as_dict(self) -> dict:
        return {"id": self.id, "user_id": self.user_id, "book_id": self.book_id}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UserFilter id={self.id} user_id={self.user_id} book_id={self.book_id}>"


__all__ = ["Base", "UserFilter"]


# ---------------- Mozello Integration (notification settings storage) ---------------

class MozelloConfig(Base):
    """Singleton table storing Mozello API integration settings.

    We intentionally keep a single row (id=1). `notifications_wanted` is stored
    as JSON text (list of event strings) for simplicity – small payload.
    """
    __tablename__ = "mozello_config"

    id = Column(Integer, primary_key=True, default=1)
    api_key = Column(String(128), nullable=True)
    notifications_url = Column(String(500), nullable=True)
    notifications_wanted = Column(Text, nullable=True)  # JSON array
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    ALLOWED_EVENTS = [
        "ORDER_CREATED",
        "ORDER_DELETED",
        "PAYMENT_CHANGED",
        "DISPATCH_CHANGED",
        "PRODUCT_CHANGED",
        "PRODUCT_DELETED",
        "STOCK_CHANGED",
    ]

    def set_events(self, events):
        cleaned = [e for e in events if e in self.ALLOWED_EVENTS]
        self.notifications_wanted = json.dumps(cleaned)

    def events_list(self):
        if not self.notifications_wanted:
            return []
        try:
            return json.loads(self.notifications_wanted)
        except Exception:
            return []

    def as_dict(self):
        return {
            "api_key_set": bool(self.api_key),  # do not expose raw key here
            "notifications_url": self.notifications_url,
            "notifications_wanted": self.events_list(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

__all__.append("MozelloConfig")
