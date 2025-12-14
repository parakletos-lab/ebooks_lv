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
		if scope == CatalogScope.PURCHASED:
			if not isinstance(state, UserCatalogState):
				return and_(base_clause, false())
			ids = state.purchased_book_ids
			if not ids:
				return and_(base_clause, false())
			return and_(base_clause, Books.id.in_(sorted(ids)))
		if scope == CatalogScope.FREE:
			if not isinstance(state, UserCatalogState):
				return and_(base_clause, false())
			free_ids = state.free_book_ids
			if not free_ids:
				return and_(base_clause, false())
			return and_(base_clause, Books.id.in_(sorted(free_ids)))
		return base_clause

	CalibreDB.common_filters = _patched  # type: ignore[assignment]
	setattr(CalibreDB, "_users_books_common_filters", True)
	LOG.debug("Patched CalibreDB.common_filters for purchased scope filtering")


def _patch_read_book_access(app: Any) -> None:
	"""Allow anonymous reading of free books.

	We avoid modifying Calibre-Web sources by replacing the registered Flask
	view function for endpoint `web.read_book`.
	"""
	try:
		from cps.usermanagement import login_required_if_no_ano  # type: ignore
		from cps.cw_login import current_user  # type: ignore
		from flask import abort, g as flask_g  # type: ignore
	except Exception:  # pragma: no cover
		LOG.warning("Unable to import Calibre-Web auth helpers; read_book patch skipped")
		return

	view_functions = getattr(app, "view_functions", None)
	if not isinstance(view_functions, dict):  # pragma: no cover
		return
	if getattr(app, "_ebookslv_read_book_patched", False):  # type: ignore[attr-defined]
		return

	original = view_functions.get("web.read_book")
	if not callable(original):
		LOG.warning("web.read_book endpoint not found; read_book patch skipped")
		return

	# Unwrap decorators applied in cps.web: login_required_if_no_ano(viewer_required(read_book))
	inner = getattr(original, "__wrapped__", None)
	if inner is None:
		LOG.warning("web.read_book has no __wrapped__; cannot patch safely")
		return
	raw = getattr(inner, "__wrapped__", None)
	if raw is None:
		LOG.warning("web.read_book inner wrapper has no __wrapped__; cannot patch safely")
		return

	def _can_view_free(book_id: Any) -> bool:
		try:
			state = getattr(flask_g, "catalog_state", None)
			exists = state is not None and hasattr(state, "is_free")
			return bool(exists and state.is_free(book_id))  # type: ignore[attr-defined]
		except Exception:
			return False

	def _patched_read_book(book_id, book_format):  # type: ignore[no-untyped-def]
		if current_user.role_viewer():
			return raw(book_id, book_format)
		if _can_view_free(book_id):
			return raw(book_id, book_format)
		abort(403)

	view_functions["web.read_book"] = login_required_if_no_ano(_patched_read_book)
	setattr(app, "_ebookslv_read_book_patched", True)
	LOG.debug("Patched web.read_book to allow anonymous free-book reading")


def _patch_serve_book_access(app: Any) -> None:
	"""Allow anonymous fetching of free-book reader assets.

	Calibre-Web serves ebook files used by the in-browser reader via
	`web.serve_book` (routes: `/show/<book_id>/<format>/...`). If we allow
	anonymous access to `/read/...` for free books, we must also allow the
	corresponding `/show/...` requests or the reader will spin forever.

	We avoid modifying Calibre-Web sources by replacing the registered Flask
	view function for endpoint `web.serve_book`.
	"""
	try:
		from cps.usermanagement import login_required_if_no_ano  # type: ignore
		from cps.cw_login import current_user  # type: ignore
		from flask import abort, g as flask_g  # type: ignore
	except Exception:  # pragma: no cover
		LOG.warning("Unable to import Calibre-Web auth helpers; serve_book patch skipped")
		return

	view_functions = getattr(app, "view_functions", None)
	if not isinstance(view_functions, dict):  # pragma: no cover
		return
	if getattr(app, "_ebookslv_serve_book_patched", False):  # type: ignore[attr-defined]
		return

	original = view_functions.get("web.serve_book")
	if not callable(original):
		LOG.warning("web.serve_book endpoint not found; serve_book patch skipped")
		return

	# Unwrap decorators applied in cps.web: login_required_if_no_ano(viewer_required(serve_book))
	inner = getattr(original, "__wrapped__", None)
	if inner is None:
		LOG.warning("web.serve_book has no __wrapped__; cannot patch safely")
		return
	raw = getattr(inner, "__wrapped__", None)
	if raw is None:
		LOG.warning("web.serve_book inner wrapper has no __wrapped__; cannot patch safely")
		return

	def _can_view_free(book_id: Any) -> bool:
		try:
			state = getattr(flask_g, "catalog_state", None)
			exists = state is not None and hasattr(state, "is_free")
			return bool(exists and state.is_free(book_id))  # type: ignore[attr-defined]
		except Exception:
			return False

	def _patched_serve_book(book_id, book_format, anyname):  # type: ignore[no-untyped-def]
		if current_user.role_viewer():
			return raw(book_id, book_format, anyname)
		if _can_view_free(book_id):
			return raw(book_id, book_format, anyname)
		abort(403)

	view_functions["web.serve_book"] = login_required_if_no_ano(_patched_serve_book)
	setattr(app, "_ebookslv_serve_book_patched", True)
	LOG.debug("Patched web.serve_book to allow anonymous free-book reading")


def register_calibre_overrides(app: Any) -> None:  # pragma: no cover - glue code
	if getattr(app, "_users_books_calibre_overrides", False):  # type: ignore[attr-defined]
		return
	_patch_common_filters()
	_patch_read_book_access(app)
	_patch_serve_book_access(app)
	setattr(app, "_users_books_calibre_overrides", True)


__all__ = ["register_calibre_overrides"]
