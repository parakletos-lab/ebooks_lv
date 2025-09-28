"""users_books ORM models (migrated from legacy plugin).

Original source: plugins.users_books.models
Purpose: define per-user allow list mapping table.
"""
from __future__ import annotations

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, UniqueConstraint, Index

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
