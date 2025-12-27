"""Disable rating filter on advanced search when ratings section is hidden."""

from __future__ import annotations

from typing import Any

from flask import Response, request

from app.utils.logging import get_logger

LOG = get_logger("advsearch_rating_injection")


def _should_inject(response: Response) -> bool:
    if response.status_code != 200:
        return False
    ctype = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in ctype:
        return False
    body = response.get_data(as_text=False)
    if not body:
        return False
    # Only the advanced search form page.
    return (request.path or "") == "/advsearch"


def _user_has_ratings_section() -> bool:
    try:
        from cps.cw_login import current_user  # type: ignore
        from cps import constants as cw_constants  # type: ignore

        if not getattr(current_user, "is_authenticated", False):
            return False
        checker = getattr(current_user, "check_visibility", None)
        if callable(checker):
            return bool(checker(getattr(cw_constants, "SIDEBAR_RATING")))
    except Exception:
        return True  # fail open if runtime is unusual
    return True


def _inject_disable_rating_filter(response: Response) -> None:
    body_text = response.get_data(as_text=True)
    if not body_text or "ratinghigh" not in body_text:
        return
    if "data-eblv-disable-advsearch-rating" in body_text:
        return

    script = """
<script data-eblv-disable-advsearch-rating="1">
(function () {
  function disable() {
    var high = document.getElementById('ratinghigh');
    var low = document.getElementById('ratinglow');
    if (high) {
      high.value = '';
      high.disabled = true;
    }
    if (low) {
      low.value = '';
      low.disabled = true;
    }
    var row = null;
    if (high && high.closest) row = high.closest('.row');
    if (!row && low && low.closest) row = low.closest('.row');
    if (row) row.style.display = 'none';
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', disable);
  } else {
    disable();
  }
})();
</script>
""".strip()

    if "</body>" in body_text:
        body_text = body_text.replace("</body>", script + "</body>", 1)
        response.set_data(body_text)


def register_advsearch_rating_injection(app: Any) -> None:
    if getattr(app, "_ebookslv_advsearch_rating_injection", False):  # type: ignore[attr-defined]
        return

    @app.after_request  # type: ignore[misc]
    def _after(response: Response):
        try:
            if not _should_inject(response):
                return response
            if _user_has_ratings_section():
                return response
            _inject_disable_rating_filter(response)
        except Exception:
            LOG.debug("advsearch rating injection failed", exc_info=True)
        return response

    setattr(app, "_ebookslv_advsearch_rating_injection", True)


__all__ = ["register_advsearch_rating_injection"]
