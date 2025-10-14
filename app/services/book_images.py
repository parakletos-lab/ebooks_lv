"""Book extra images service layer.

Manages per-book extra image gallery stored under the Calibre library.
Provides helpers used by admin routes and future sync workers.
"""
from __future__ import annotations

import base64
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from werkzeug.datastructures import FileStorage  # type: ignore

from app.services import books_sync
from app.services import mozello_service
from app.utils.logging import get_logger

LOG = get_logger("book_images")

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGES_PER_BOOK = 10
MAX_TOTAL_BYTES_PER_BOOK = 15 * 1024 * 1024
GALLERY_DIRNAME = "extra_images"
MANIFEST_NAME = "extra_images_manifest.json"


@dataclass
class ManifestEntry:
    name: str
    sha256: str
    uploaded_remote: bool = False
    remote_uid: Optional[str] = None
    pending_remote: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "ManifestEntry":
        return cls(
            name=str(data.get("name")),
            sha256=str(data.get("sha256")),
            uploaded_remote=bool(data.get("uploaded_remote", False)),
            remote_uid=data.get("remote_uid") or None,
            pending_remote=bool(data.get("pending_remote", False)),
        )

    def to_dict(self) -> Dict[str, object]:
        out: Dict[str, object] = {
            "name": self.name,
            "sha256": self.sha256,
            "uploaded_remote": self.uploaded_remote,
        }
        if self.remote_uid:
            out["remote_uid"] = self.remote_uid
        if self.pending_remote:
            out["pending_remote"] = self.pending_remote
        return out


def _library_root() -> Path:
    root = os.getenv("CALIBRE_LIBRARY_PATH") or books_sync.DEFAULT_LIBRARY_ROOT
    return Path(root)


def get_book_path(book_id: int) -> Optional[str]:
    """Return absolute path to a book directory or None if not found."""
    rel = books_sync.get_book_relative_path(book_id)
    if not rel:
        return None
    abs_path = (_library_root() / rel).resolve()
    library_root = _library_root().resolve()
    if not str(abs_path).startswith(str(library_root)):
        LOG.warning("book path traversal guard triggered book_id=%s path=%s", book_id, abs_path)
        return None
    if not abs_path.exists():
        LOG.warning("book directory missing book_id=%s path=%s", book_id, abs_path)
        return None
    return str(abs_path)


def _gallery_dir(book_id: int) -> Optional[Path]:
    base = get_book_path(book_id)
    if not base:
        return None
    gallery = Path(base) / GALLERY_DIRNAME
    return gallery


def _manifest_path(book_id: int) -> Optional[Path]:
    gallery = _gallery_dir(book_id)
    if not gallery:
        return None
    return gallery / MANIFEST_NAME


def _ensure_gallery_dir(gallery: Path) -> bool:
    try:
        gallery.mkdir(mode=0o755, parents=True, exist_ok=True)
        return True
    except Exception as exc:  # pragma: no cover - filesystem
        LOG.error("failed to ensure gallery dir=%s err=%s", gallery, exc)
        return False


def _read_manifest(manifest_path: Path) -> List[ManifestEntry]:
    if not manifest_path.exists():
        return []
    try:
        with manifest_path.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        files = raw.get("files", []) if isinstance(raw, dict) else []
        entries = []
        for item in files:
            try:
                entries.append(ManifestEntry.from_dict(item))
            except Exception:
                LOG.debug("skipping malformed manifest entry: %s", item)
        return entries
    except Exception as exc:
        LOG.warning("manifest read failed path=%s err=%s", manifest_path, exc)
        return []


def _write_manifest(manifest_path: Path, entries: List[ManifestEntry]) -> bool:
    tmp_fd = None
    tmp_path = None
    try:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=str(manifest_path.parent), prefix="manifest-", suffix=".tmp")
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            payload = {"files": [e.to_dict() for e in entries]}
            json.dump(payload, fh, ensure_ascii=True, separators=(",", ":"))
        os.replace(tmp_path, manifest_path)
        return True
    except Exception as exc:  # pragma: no cover - filesystem
        LOG.error("manifest write failed path=%s err=%s", manifest_path, exc)
        if tmp_fd:
            try:
                os.close(tmp_fd)
            except Exception:
                pass
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return False


def _load_existing(book_id: int) -> Tuple[Path, Path, List[ManifestEntry]]:
    gallery = _gallery_dir(book_id)
    if gallery is None:
        raise FileNotFoundError("book_not_found")
    if not _ensure_gallery_dir(gallery):
        raise IOError("io_error")
    manifest_path = gallery / MANIFEST_NAME
    entries = _read_manifest(manifest_path)
    return gallery, manifest_path, entries


def _safe_target_path(gallery: Path, filename: str) -> Optional[Path]:
    target = (gallery / filename).resolve()
    if not str(target).startswith(str(gallery.resolve())):
        return None
    return target


def _hash_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _total_bytes(gallery: Path) -> int:
    total = 0
    for item in gallery.iterdir():
        if item.is_file() and item.name != MANIFEST_NAME:
            total += item.stat().st_size
    return total


def list_images(book_id: int) -> Dict[str, object]:
    try:
        gallery, manifest_path, entries = _load_existing(book_id)
    except FileNotFoundError:
        return {"files": [], "count": 0, "limit": MAX_IMAGES_PER_BOOK}
    except IOError:
        return {"files": [], "count": 0, "limit": MAX_IMAGES_PER_BOOK}

    items: List[Dict[str, object]] = []
    for entry in entries:
        target = gallery / entry.name
        if not target.exists():
            continue
        stat = target.stat()
        items.append({
            "name": entry.name,
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "uploaded_remote": entry.uploaded_remote,
            "remote_uid": entry.remote_uid,
            "pending_remote": entry.pending_remote,
        })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": items, "count": len(items), "limit": MAX_IMAGES_PER_BOOK}


def _validate_upload(existing_entries: List[ManifestEntry], gallery: Path, file_storage: FileStorage) -> Optional[str]:
    if not file_storage:
        return "file_missing"
    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        return "unsupported_type"
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size <= 0:
        return "file_missing"
    if size > MAX_IMAGE_BYTES:
        return "file_too_large"
    if len(existing_entries) >= MAX_IMAGES_PER_BOOK:
        return "limit_reached"
    current_total = _total_bytes(gallery)
    if current_total + size > MAX_TOTAL_BYTES_PER_BOOK:
        return "limit_reached"
    return None


def _generate_filename(ext: str) -> str:
    rand = os.urandom(4).hex()
    epoch_ms = int(time.time() * 1000)
    return f"img-{epoch_ms}-{rand}.{ext}"


def save_image(book_id: int, file_storage: FileStorage) -> Tuple[bool, Dict[str, object]]:
    try:
        gallery, manifest_path, entries = _load_existing(book_id)
    except FileNotFoundError:
        return False, {"error": "book_not_found"}
    except IOError:
        return False, {"error": "io_error"}

    err = _validate_upload(entries, gallery, file_storage)
    if err:
        return False, {"error": err}

    original_name = file_storage.filename or ""
    ext = original_name.rsplit(".", 1)[-1].lower()
    safe_name = _generate_filename(ext)
    target = _safe_target_path(gallery, safe_name)
    if not target:
        return False, {"error": "io_error"}

    try:
        file_storage.save(str(target))
    except Exception as exc:  # pragma: no cover - filesystem failure
        LOG.error("failed saving image book_id=%s err=%s", book_id, exc)
        return False, {"error": "io_error"}

    try:
        sha = _hash_file(target)
    except Exception as exc:  # pragma: no cover
        LOG.error("sha compute failed book_id=%s file=%s err=%s", book_id, target, exc)
        target.unlink(missing_ok=True)
        return False, {"error": "io_error"}

    # dedupe
    for entry in entries:
        if entry.sha256 == sha:
            LOG.info("dedupe hit book_id=%s filename=%s existing=%s", book_id, safe_name, entry.name)
            target.unlink(missing_ok=True)
            existing_target = gallery / entry.name
            if not existing_target.exists():
                break
            stat = existing_target.stat()
            image_info = {
                "name": entry.name,
                "size": stat.st_size,
                "mtime": int(stat.st_mtime),
                "uploaded_remote": entry.uploaded_remote,
                "remote_uid": entry.remote_uid,
                "pending_remote": entry.pending_remote,
                "deduped": True,
            }
            return True, {"image": image_info, "deduped": True, "pending_remote": entry.pending_remote}

    stat = target.stat()
    new_entry = ManifestEntry(name=safe_name, sha256=sha, uploaded_remote=False, remote_uid=None, pending_remote=True)
    entries.append(new_entry)
    if not _write_manifest(manifest_path, entries):
        target.unlink(missing_ok=True)
        return False, {"error": "io_error"}

    image_info = {
        "name": safe_name,
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "uploaded_remote": False,
        "remote_uid": None,
        "pending_remote": True,
    }
    return True, {"image": image_info, "pending_remote": True}


def delete_image(book_id: int, filename: str, delete_remote: bool = False) -> Tuple[bool, Dict[str, object]]:
    try:
        gallery, manifest_path, entries = _load_existing(book_id)
    except FileNotFoundError:
        return False, {"error": "book_not_found"}
    except IOError:
        return False, {"error": "io_error"}

    target = _safe_target_path(gallery, filename)
    if not target or not target.exists():
        return False, {"error": "file_missing"}

    remaining: List[ManifestEntry] = []
    removed_entry: Optional[ManifestEntry] = None
    for entry in entries:
        if entry.name == filename:
            removed_entry = entry
            continue
        remaining.append(entry)

    mozello_result: Dict[str, object] = {"attempted": False, "deleted": False}
    if delete_remote and removed_entry and removed_entry.remote_uid:
        handle = books_sync.get_mz_handle(book_id)
        if handle:
            mozello_result["attempted"] = True
            ok_remote, remote_info = mozello_service.delete_product_picture(handle, removed_entry.remote_uid)
            mozello_result["deleted"] = ok_remote
            if not ok_remote:
                mozello_result["error"] = remote_info.get("error", "upload_failed")
        else:
            mozello_result["error"] = "handle_missing"

    try:
        target.unlink()
    except Exception as exc:  # pragma: no cover
        LOG.error("failed removing image book_id=%s file=%s err=%s", book_id, filename, exc)
        return False, {"error": "io_error"}

    if not _write_manifest(manifest_path, remaining):
        return False, {"error": "io_error"}

    payload: Dict[str, object] = {"ok": True}
    if mozello_result.get("attempted"):
        payload["mozello"] = mozello_result
    return True, payload


def encode_image_base64(book_id: int, filename: str) -> Tuple[bool, Dict[str, object]]:
    gallery = _gallery_dir(book_id)
    if not gallery:
        return False, {"error": "book_not_found"}
    target = _safe_target_path(gallery, filename)
    if not target or not target.exists():
        return False, {"error": "file_missing"}
    size = target.stat().st_size
    if size > MAX_IMAGE_BYTES:
        return False, {"error": "file_too_large"}
    try:
        with target.open("rb") as fh:
            data = fh.read()
        encoded = base64.b64encode(data).decode("ascii")
        return True, {"data": encoded, "size": size}
    except Exception as exc:  # pragma: no cover
        LOG.error("encode base64 failed book_id=%s file=%s err=%s", book_id, filename, exc)
        return False, {"error": "io_error"}


def mark_remote_uploaded(book_id: int, filename: str, remote_uid: str) -> bool:
    try:
        gallery, manifest_path, entries = _load_existing(book_id)
    except (FileNotFoundError, IOError):
        return False
    updated = False
    for entry in entries:
        if entry.name == filename:
            entry.remote_uid = remote_uid
            entry.uploaded_remote = True
            entry.pending_remote = False
            updated = True
            break
    if not updated:
        return False
    return _write_manifest(manifest_path, entries)


def mark_remote_pending(book_id: int, filename: str) -> bool:
    try:
        _, manifest_path, entries = _load_existing(book_id)
    except (FileNotFoundError, IOError):
        return False
    changed = False
    for entry in entries:
        if entry.name == filename:
            entry.pending_remote = True
            changed = True
    if not changed:
        return False
    return _write_manifest(manifest_path, entries)


__all__ = [
    "ALLOWED_EXT",
    "MAX_IMAGE_BYTES",
    "MAX_IMAGES_PER_BOOK",
    "MAX_TOTAL_BYTES_PER_BOOK",
    "GALLERY_DIRNAME",
    "get_book_path",
    "list_images",
    "save_image",
    "delete_image",
    "encode_image_base64",
    "mark_remote_uploaded",
    "mark_remote_pending",
]
