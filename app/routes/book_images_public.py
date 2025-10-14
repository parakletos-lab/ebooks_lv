"""Public endpoints exposing extra book images."""
from __future__ import annotations

import mimetypes
from typing import Any

try:  # runtime guard for tests
    from flask import Blueprint, jsonify, send_file, abort
    from flask import request as flask_request  # noqa: F401  # reserved for future ACL hooks
except Exception:  # pragma: no cover
    Blueprint = object  # type: ignore
    def jsonify(*args: Any, **kwargs: Any):  # type: ignore
        raise RuntimeError("Flask not available")
    def send_file(*args: Any, **kwargs: Any):  # type: ignore
        raise RuntimeError("Flask not available")
    def abort(code: int):  # type: ignore
        raise RuntimeError(code)

from app.services import book_images

bp = Blueprint("ebookslv_public", __name__, url_prefix="/ebookslv")


def _build_public_url(book_id: int, name: str) -> str:
    from flask import url_for

    return url_for("ebookslv_public.get_book_image", book_id=book_id, filename=name)


def _is_public_allowed(book_id: int) -> bool:
    # ACL placeholder; currently all public.
    return True


@bp.route("/book/<int:book_id>/images.json", methods=["GET"])
def get_book_images_json(book_id: int):
    if not _is_public_allowed(book_id):
        return jsonify({"images": []}), 403
    data = book_images.list_images(book_id)
    images = data.get("files", []) if isinstance(data, dict) else []
    output = []
    for entry in images:
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        output.append({
            "name": name,
            "url": _build_public_url(book_id, name),
        })
    return jsonify({"images": output})


@bp.route("/book/<int:book_id>/image/<path:filename>", methods=["GET"])
def get_book_image(book_id: int, filename: str):
    if not _is_public_allowed(book_id):
        abort(403)
    gallery_path = book_images.get_book_path(book_id)
    if not gallery_path:
        abort(404)
    from pathlib import Path

    base = Path(gallery_path) / book_images.GALLERY_DIRNAME
    target = (base / filename).resolve()
    if not str(target).startswith(str(base.resolve())):
        abort(404)
    if not target.exists() or not target.is_file():
        abort(404)
    # Optional thumb placeholder support via query params (future)
    mimetype, _ = mimetypes.guess_type(target.name)
    if mimetype is None:
        mimetype = "application/octet-stream"
    return send_file(str(target), mimetype=mimetype, conditional=True, download_name=target.name)


def register_public_blueprint(app: Any) -> None:
    if not getattr(app, "_ebookslv_public_bp", None):
        app.register_blueprint(bp)
        setattr(app, "_ebookslv_public_bp", bp)


__all__ = ["register_public_blueprint", "bp"]
