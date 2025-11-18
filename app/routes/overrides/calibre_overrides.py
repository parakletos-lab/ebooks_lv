"""Calibre-Web override hooks (runtime monkey patches)."""
from __future__ import annotations

from typing import Any, Callable

from flask import g
from sqlalchemy import and_, false

from app.routes.overrides.catalog_access import CatalogScope
from app.services.catalog_access import UserCatalogState
from app.utils.logging import get_logger

LOG = get_logger("calibre_overrides")


def _patch_common_filters() -> None:
	try:
		from cps import db as cw_db  # type: ignore
	except Exception:  # pragma: no cover
		LOG.warning("Unable to import Calibre-Web db module; common_filters patch skipped")
		return

	CalibreDB = getattr(cw_db, "CalibreDB", None)
	Books = getattr(cw_db, "Books", None)
	if not CalibreDB or not Books:
		LOG.warning("CalibreDB/Books symbols missing; cannot patch common_filters")
		return

	if getattr(CalibreDB, "_users_books_common_filters", False):  # type: ignore[attr-defined]
		return

	original: Callable[..., Any] = CalibreDB.common_filters  # type: ignore[assignment]

	def _patched(self, allow_show_archived: bool = False, return_all_languages: bool = False):  # type: ignore[override]
		base_clause = original(self, allow_show_archived, return_all_languages)
		try:
			scope = getattr(g, "catalog_scope", CatalogScope.ALL)
			state = getattr(g, "catalog_state", None)
		except RuntimeError:  # outside request context
			return base_clause
		if scope != CatalogScope.PURCHASED:
			return base_clause
		if not isinstance(state, UserCatalogState):
			return and_(base_clause, false())
		ids = state.purchased_book_ids
		if not ids:
			return and_(base_clause, false())
		return and_(base_clause, Books.id.in_(sorted(ids)))

	CalibreDB.common_filters = _patched  # type: ignore[assignment]
	setattr(CalibreDB, "_users_books_common_filters", True)
	LOG.debug("Patched CalibreDB.common_filters for purchased scope filtering")


def register_calibre_overrides(app: Any) -> None:  # pragma: no cover - glue code
	if getattr(app, "_users_books_calibre_overrides", False):  # type: ignore[attr-defined]
		return
	_patch_common_filters()
	setattr(app, "_users_books_calibre_overrides", True)


__all__ = ["register_calibre_overrides"]
