"""Language switch endpoint for users and anonymous visitors."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session, url_for

try:  # pragma: no cover - Flask-Babel optional in tests
    from flask_babel import gettext as _  # type: ignore
except Exception:  # pragma: no cover
    def _(message, **kwargs):  # type: ignore
        if kwargs:
            try:
                return message % kwargs
            except Exception:
                return message
        return message

try:  # runtime dependency (optional)
    from cps import csrf  # type: ignore
except Exception:  # pragma: no cover
    csrf = None  # type: ignore

from app.i18n.preferences import SESSION_LOCALE_KEY, SUPPORTED_LANGUAGES, normalize_language_choice
from app.services import calibre_users_service
from app.services.calibre_users_service import LanguageUpdateError
from app.utils.identity import get_current_user_id
from app.utils.logging import get_logger

LOG = get_logger("language_switch")

bp = Blueprint("language_switch", __name__)


def _maybe_exempt(func):  # type: ignore
    if csrf:  # type: ignore
        try:
            return csrf.exempt(func)  # type: ignore[arg-type]
        except Exception:  # pragma: no cover
            return func
    return func


@bp.route("/language/switch", methods=["POST", "GET"])
@_maybe_exempt
def switch_language():  # pragma: no cover - integration tested via Flask client
    payload = request.get_json(silent=True) or {}
    raw_lang = payload.get("language") or request.values.get("language") or request.values.get("lang")
    normalized = normalize_language_choice(raw_lang)
    if not normalized:
        return jsonify({"error": "unsupported_language", "supported": SUPPORTED_LANGUAGES}), 400

    session[SESSION_LOCALE_KEY] = normalized
    session.modified = True

    user_id = get_current_user_id()
    if user_id:
        try:
            calibre_users_service.update_language_preference(user_id, normalized)
        except LanguageUpdateError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # pragma: no cover - defensive
            LOG.warning("Language update failed user_id=%s: %s", user_id, exc)
            return jsonify({"error": "update_language_failed"}), 500

    target = request.values.get("next") or request.referrer or url_for("web.index")
    return jsonify({"status": "ok", "language": normalized, "redirect": target})


def register_language_switch(app):  # pragma: no cover - glue code
    if getattr(app, "_users_books_language_switch", False):  # type: ignore[attr-defined]
        return
    app.register_blueprint(bp)
    setattr(app, "_users_books_language_switch", True)
    LOG.debug("Language switch blueprint registered")


__all__ = ["register_language_switch", "bp"]
