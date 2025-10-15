"""ORM models for users_books DB (Mozello orders + config)."""
from __future__ import annotations

import datetime
import json

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MozelloOrder(Base):
    """Mozello order import table (repurposed legacy users_books DB).

    Stores email ↔ Mozello handle combinations with optional links to
    Calibre users/books. Each (email, mz_handle) pair is unique.
    """

    __tablename__ = "users_books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    mz_handle = Column(String(255), nullable=False, index=True)
    calibre_user_id = Column(Integer, nullable=True, index=True)
    calibre_book_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("email", "mz_handle", name="uq_mozello_order_email_handle"),
        Index("ix_users_books_handle_email", "mz_handle", "email"),
    )

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "mz_handle": self.mz_handle,
            "calibre_user_id": self.calibre_user_id,
            "calibre_book_id": self.calibre_book_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            "<MozelloOrder id={0} email={1} mz_handle={2} user_id={3} book_id={4}>".format(
                self.id,
                self.email,
                self.mz_handle,
                self.calibre_user_id,
                self.calibre_book_id,
            )
        )


# Backward compatible alias for any legacy imports that still reference
# the old name. Remove once callers migrate fully.
UserFilter = MozelloOrder

__all__ = ["Base", "MozelloOrder", "UserFilter"]


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
    forced_port = Column(String(10), nullable=True)  # optional explicit port for webhook URL
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
            "forced_port": self.forced_port,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

__all__.append("MozelloConfig")
