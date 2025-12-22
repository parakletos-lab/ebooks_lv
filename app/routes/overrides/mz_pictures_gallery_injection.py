"""Mozello additional pictures gallery injection for book detail pages.

Adds a Mozello-like thumbnail strip below the main cover on the Calibre-Web
book detail page without modifying upstream /calibre-web templates.

Data source:
- `mz_pictures` identifier: JSON list of {uid,url}
- `mz_cover_uids` identifier: JSON list of uid strings used for the main cover

Behavior:
- The strip is shown only when there are additional images in `mz_pictures`
	excluding the ones referenced by `mz_cover_uids`.
- Clicking a thumbnail opens it fullscreen using the same fullscreen mechanism
	as clicking the main cover (temporarily swapping the cover image src).
"""

from __future__ import annotations

import json
import re
from string import Template
from typing import Any, List, Tuple
from urllib.parse import urlparse

from flask import Request, Response, request

from app.services import books_sync
from app.utils.logging import get_logger

LOG = get_logger("mz_pictures_gallery_injection")

MARKER = "ub-mz-pictures-gallery"
MAX_BODY_SIZE = 1_500_000  # bytes


def _is_target_request(req: Request) -> Tuple[bool, int | None]:
		path = (req.path or "").rstrip("/")
		match = re.match(r"^/book/(\d+)$", path)
		if not match:
				return False, None
		try:
				return True, int(match.group(1))
		except Exception:
				return False, None


def _should_skip(response: Response) -> Tuple[bool, str, int | None]:
		is_target, book_id = _is_target_request(request)
		if not is_target:
				return True, "not_detail", None
		if response.status_code != 200:
				return True, f"status_{response.status_code}", book_id
		ctype = (response.headers.get("Content-Type") or "").lower()
		if "text/html" not in ctype:
				return True, f"ctype_{ctype or 'none'}", book_id
		body = response.get_data(as_text=False)
		if not body:
				return True, "empty_body", book_id
		if len(body) > MAX_BODY_SIZE:
				return True, "body_too_large", book_id
		if MARKER.encode("utf-8") in body:
				return True, "marker_present", book_id
		if b"id=\"detailcover\"" not in body:
				return True, "detailcover_missing", book_id
		return False, "ok", book_id


def _js(value: Any) -> str:
		return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _build_snippet(extra_urls: List[str]) -> bytes:
		script = Template(
				"""
<script data-$marker="1">
(function() {
	'use strict';

	var urls = $urls;
	if (!Array.isArray(urls) || urls.length === 0) { return; }

	function ensureGallery(root) {
		root = root || document;
		var cover = root.querySelector('#detailcover');
		if (!cover) { return; }
		if (root.querySelector('[data-ub-mz-gallery="1"]')) { return; }

		var coverContainer = cover.closest('.cover') || cover.parentElement;
		if (!coverContainer || !coverContainer.parentElement) { return; }

		// Store the original src once, so we can restore after fullscreen exit.
		if (!cover.dataset.ubOrigSrc) {
			cover.dataset.ubOrigSrc = cover.getAttribute('src') || cover.src || '';
		}

		function isFullscreen() {
			return !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
		}

		function restoreCoverIfNeeded() {
			if (isFullscreen()) { return; }
			if (cover.dataset.ubTempSrc && cover.dataset.ubOrigSrc) {
				cover.setAttribute('src', cover.dataset.ubOrigSrc);
				delete cover.dataset.ubTempSrc;
			}
		}

		if (!window.__ubMzGalleryFullscreenHook) {
			window.__ubMzGalleryFullscreenHook = true;
			document.addEventListener('fullscreenchange', restoreCoverIfNeeded);
			document.addEventListener('webkitfullscreenchange', restoreCoverIfNeeded);
			document.addEventListener('mozfullscreenchange', restoreCoverIfNeeded);
			document.addEventListener('MSFullscreenChange', restoreCoverIfNeeded);
		}

		var gallery = document.createElement('div');
		gallery.setAttribute('data-ub-mz-gallery', '1');
		gallery.className = 'ub-mz-gallery';

		urls.forEach(function(url) {
			if (!url) { return; }

			// Tile wrapper makes height:100% meaningful and keeps a consistent grid.
			var tile = document.createElement('div');
			tile.className = 'ub-mz-gallery__tile';

			var img = document.createElement('img');
			img.alt = '';
			img.src = url;
			img.className = 'ub-mz-gallery__img';
			img.addEventListener('click', function() {
				if (!cover.dataset.ubOrigSrc) {
					cover.dataset.ubOrigSrc = cover.getAttribute('src') || cover.src || '';
				}
				cover.dataset.ubTempSrc = url;
				cover.setAttribute('src', url);

				if (isFullscreen()) {
					return;
				}
				// Fullscreen API requires a real user gesture. Calling the upstream helper
				// directly from THIS click handler preserves that gesture.
				if (typeof window.toggleFullscreen === 'function') {
					window.toggleFullscreen(cover);
					return;
				}
				// Fallback: directly request fullscreen.
				var req = cover.requestFullscreen || cover.webkitRequestFullscreen || cover.mozRequestFullScreen || cover.msRequestFullscreen;
				if (req) { req.call(cover); }
			});

			tile.appendChild(img);
			gallery.appendChild(tile);
		});

		coverContainer.parentElement.insertBefore(gallery, coverContainer.nextSibling);
	}

	function init() {
		ensureGallery(document);
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}

	// When rendered into the modal via AJAX, ensure we bind after it is shown.
	if (window.jQuery && typeof window.jQuery === 'function' && window.jQuery.fn && window.jQuery.fn.modal) {
		window.jQuery('#bookDetailsModal').on('shown.bs.modal', function() {
			ensureGallery(document);
		});
	}
})();
</script>
"""
		)

		rendered = script.substitute(marker=MARKER, urls=_js(extra_urls))
		return rendered.encode("utf-8")


def _inject(response: Response, extra_urls: List[str]) -> Response:
		body = response.get_data(as_text=False)
		if not body:
				return response
		snippet = _build_snippet(extra_urls)
		lower_body = body.lower()
		closing = lower_body.rfind(b"</body>")
		if closing == -1:
				response.set_data(body + snippet)
				return response
		response.set_data(body[:closing] + snippet + body[closing:])
		return response


def _extract_external_img_sources(urls: List[str]) -> List[str]:
		seen: set[str] = set()
		out: List[str] = []
		for url in urls:
				if not url:
						continue
				# Relative and absolute-path URLs are same-origin.
				if url.startswith("/"):
						continue
				# Scheme-relative URLs (//example.com/path)
				if url.startswith("//"):
						parsed = urlparse("https:" + url)
				else:
						parsed = urlparse(url)
				scheme = (parsed.scheme or "").lower()
				netloc = parsed.netloc
				if scheme not in {"http", "https"} or not netloc:
						continue
				origin = f"{scheme}://{netloc}"
				if origin in seen:
						continue
				seen.add(origin)
				out.append(origin)
		return out


def _extend_csp_img_src(resp: Response, external_sources: List[str]) -> None:
		if not external_sources:
				return
		csp = resp.headers.get("Content-Security-Policy")
		if not csp:
				return
		# Normalize any stray newlines; CSP is a single header value.
		csp = " ".join(csp.split())
		parts = [p.strip() for p in csp.split(";") if p.strip()]
		new_parts: List[str] = []
		updated = False
		for part in parts:
				tokens = part.split()
				if not tokens:
						continue
				if tokens[0].lower() != "img-src":
						new_parts.append(part)
						continue

				# Merge external sources into img-src.
				existing = set(tokens[1:])
				added_any = False
				for src in external_sources:
						if src not in existing:
							tokens.append(src)
							existing.add(src)
							added_any = True
				new_parts.append(" ".join(tokens))
				updated = updated or added_any
		# If there was no img-src directive, keep existing CSP unchanged.
		if updated:
				resp.headers["Content-Security-Policy"] = "; ".join(new_parts) + ";"


def register_mz_pictures_gallery_injection(app: Any) -> None:  # pragma: no cover - glue code
		if getattr(app, "_mz_pictures_gallery_injection", False):  # type: ignore[attr-defined]
				return

		@app.after_request  # type: ignore[misc]
		def _after(resp: Response):  # type: ignore[override]
				skip, reason, book_id = _should_skip(resp)
				if skip:
						LOG.debug("mz_pictures gallery injection skip: %s", reason)
						return resp
				if book_id is None:
						return resp

				try:
						pictures = books_sync.get_mz_pictures_for_book(book_id)
						cover_uids = set(books_sync.get_mz_cover_picture_uids_for_book(book_id))
						extra_urls = [
								p["url"]
								for p in pictures
								if p.get("uid") and p.get("url") and p.get("uid") not in cover_uids
						]
				except Exception as exc:  # pragma: no cover
						LOG.debug("mz_pictures gallery injection failed to load identifiers: %s", exc)
						return resp

				if not extra_urls:
						return resp

				# Calibre-Web sends a strict CSP (img-src 'self' data:) which blocks
				# Mozello-hosted images. Allow only the exact external origins used.
				external_sources = _extract_external_img_sources(extra_urls)
				_extend_csp_img_src(resp, external_sources)

				return _inject(resp, extra_urls)

		# Ensure this hook runs LAST (Flask runs after_request in reverse order).
		# Calibre-Web sets CSP in an after_request hook; if ours runs before it,
		# our CSP modifications would be overwritten.
		try:
				funcs = getattr(app, "after_request_funcs", {}).get(None)
				if isinstance(funcs, list) and funcs and funcs[-1] is _after:
						funcs.insert(0, funcs.pop())
		except Exception:
				pass

		setattr(app, "_mz_pictures_gallery_injection", True)
		LOG.debug("mz_pictures gallery injection registered")


__all__ = ["register_mz_pictures_gallery_injection"]