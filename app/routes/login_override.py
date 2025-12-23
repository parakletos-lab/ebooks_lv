"""Email-first /login override integrating auth tokens and password resets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from flask import (
    Blueprint,
    Response,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

try:  # runtime dependency on Calibre-Web
    from cps.render_template import render_title_template as _cw_render_title_template  # type: ignore
except Exception:  # pragma: no cover - allow unit tests without Calibre runtime
    _cw_render_title_template = None  # type: ignore

try:  # runtime dependency on Calibre-Web settings (injected into templates as `config`)
    from cps import config as cw_config  # type: ignore
except Exception:  # pragma: no cover - allow unit tests without Calibre runtime
    cw_config = None  # type: ignore

try:  # pragma: no cover - Flask-Babel optional in unit tests
    from flask_babel import gettext as _  # type: ignore
except Exception:  # pragma: no cover
    def _fallback_gettext(message, **kwargs):
        if kwargs:
            try:
                return message % kwargs
            except Exception:
                return message
        return message

    _ = _fallback_gettext  # type: ignore

try:  # pragma: no cover - flask-wtf optional at runtime
    from flask_wtf.csrf import generate_csrf  # type: ignore
except Exception:  # pragma: no cover - fallback when flask-wtf missing
    def generate_csrf():  # type: ignore
        return ""

try:  # runtime dependency on Calibre-Web
    from cps.cw_login import login_user, logout_user, current_user as cw_current_user  # type: ignore
    _HAS_CW_CURRENT_USER = True
except Exception:  # pragma: no cover - allow unit tests without Calibre runtime
    def login_user(user, remember=False):  # type: ignore
        raise RuntimeError("calibre_login_unavailable")

    def logout_user():  # type: ignore
        return None

    cw_current_user = None  # type: ignore
    _HAS_CW_CURRENT_USER = False

try:  # runtime dependency needed for SQL lookups
    from cps import ub  # type: ignore
except Exception:  # pragma: no cover - unit tests patch helpers
    ub = None  # type: ignore

try:  # prefer Calibre redirect helper for open redirect protection
    from cps.redirect import get_redirect_location as _cw_redirect  # type: ignore
except Exception:  # pragma: no cover - fallback to local sanitizer
    _cw_redirect = None  # type: ignore

from sqlalchemy import func
from werkzeug.security import check_password_hash
from urllib.parse import urlencode, urlparse

from app.services import auth_link_service, password_reset_service, email_delivery, calibre_users_service
from app.services.password_reset_service import PendingReset
from app.utils.identity import clear_identity_session, get_current_user_email, get_session_email_key, normalize_email
from app.utils.logging import get_logger
from app.i18n.preferences import SESSION_LOCALE_KEY, normalize_language_choice

LOG = get_logger("login_override")
bp = Blueprint("login_override", __name__)


@dataclass(frozen=True)
class TokenDisplay:
    token: str
    email: Optional[str]
    has_temp_password: bool
    issued_at: Optional[str]


_TOKEN_ERROR_MESSAGES = {
    "email_missing": _("Secure link is missing the account email."),
    "token_inactive": _("This secure link is no longer active."),
    "token_required": _("A secure link is required to finish signing in."),
    "invalid_token": _("This secure link is invalid. Request a new email."),
    "invalid_payload": _("Secure link payload is invalid. Request a new email."),
    "invalid_timestamp": _("Secure link timestamp is invalid."),
    "reset_token_expired": _("This secure link expired. Request a new one."),
    "email_token_mismatch": _("Secure link email does not match the requested account."),
}


def _token_error_message(code: Optional[str]) -> str:
    if not code:
        return _("Secure link cannot be used. Request a new email.")
    return _TOKEN_ERROR_MESSAGES.get(code, _("Secure link cannot be used. Request a new email."))


def _default_index() -> str:
    try:
        return url_for("web.index")
    except Exception:
        return "/"


def _sanitize_next(raw_target: Optional[str]) -> str:
    target = raw_target or None
    if _cw_redirect:  # type: ignore[truthy-bool]
        try:
            return _cw_redirect(target, "web.index")  # type: ignore[arg-type]
        except Exception:
            pass
    if target and target.startswith("/"):
        return target
    return _default_index()


def _build_token_context(token: Optional[str]) -> Tuple[Optional[TokenDisplay], Optional[str]]:
    if not token:
        return None, None
    try:
        payload = auth_link_service.decode_payload(token)
    except auth_link_service.AuthLinkError as exc:
        LOG.warning("login override token rejected: %s", exc)
        return None, _token_error_message(str(exc))
    normalized_email = normalize_email(payload.get("email"))
    if not normalized_email:
        return None, _token_error_message("email_missing")
    has_temp = bool(payload.get("temp_password"))
    try:
        if not password_reset_service.has_pending_token(email=normalized_email, initial=has_temp):
            LOG.info("login token ignored email=%s reason=pending_missing", normalized_email)
            return None, None
    except password_reset_service.PasswordResetError:
        return None, _token_error_message("token_inactive")
    return TokenDisplay(
        token=token,
        email=payload.get("email"),
        has_temp_password=bool(payload.get("temp_password")),
        issued_at=payload.get("issued_at"),
    ), None


def _extract_token_email(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    try:
        payload = auth_link_service.decode_payload(token)
    except auth_link_service.AuthLinkError:
        return None
    return normalize_email(payload.get("email"))


def _is_authenticated_session_email(email: Optional[str]) -> bool:
    normalized = normalize_email(email)
    if not normalized:
        return False
    if _HAS_CW_CURRENT_USER and cw_current_user is not None:
        try:
            if not getattr(cw_current_user, "is_authenticated", False):
                return False
            current_mail = normalize_email(getattr(cw_current_user, "email", None))
            return current_mail == normalized
        except Exception:
            return False
    session_email = normalize_email(session.get(get_session_email_key()))
    if session_email != normalized:
        return False
    return session.get("user_id") is not None


def _maybe_short_circuit_login(
    token_ctx: Optional[TokenDisplay],
    next_url: str,
    raw_token: Optional[str],
) -> Optional[Response]:
    if not next_url:
        return None
    candidate_email = token_ctx.email if token_ctx and token_ctx.email else None
    if not candidate_email:
        candidate_email = _extract_token_email(raw_token)
    token_email = normalize_email(candidate_email)
    if not token_email:
        return None
    linked_user = _fetch_user_by_email(token_email)
    if not linked_user:
        LOG.info("Auth token user missing email=%s; forcing login flow", token_email)
        _logout_current_user()
        return None
    if _is_authenticated_session_email(token_email):
        LOG.info("Auth token matches active session email=%s", token_email)
        return redirect(next_url)
    LOG.info("Auth token requires login email=%s; clearing stale session", token_email)
    _logout_current_user()
    return None


def _fetch_user_by_email(email: str) -> Any:
    normalized = normalize_email(email)
    if not normalized or ub is None:
        return None
    session_obj = getattr(ub, "session", None)
    user_model = getattr(ub, "User", None)
    if not session_obj or not user_model:
        return None
    try:
        return (
            session_obj.query(user_model)
            .filter(func.lower(user_model.email) == normalized)
            .one_or_none()
        )
    except Exception:
        LOG.warning("calibre lookup failed email=%s", normalized, exc_info=True)
        return None


def _authenticate_credentials(email: str, password: str) -> Any:
    user = _fetch_user_by_email(email)
    if not user or not password:
        return None
    stored = getattr(user, "password", None)
    if not stored:
        return None
    if not check_password_hash(str(stored), password):
        return None
    return user


def _set_identity_session(user: Any, normalized_email: str) -> None:
    try:
        session["user_id"] = int(getattr(user, "id", 0))
    except (TypeError, ValueError):
        session["user_id"] = getattr(user, "id", 0)
    email_key = get_session_email_key()
    session[email_key] = normalized_email

    locale = normalize_language_choice(getattr(user, "locale", None))
    if locale:
        session[SESSION_LOCALE_KEY] = locale


def _perform_login(user: Any, remember: bool, normalized_email: str) -> None:
    login_user(user, remember=remember)
    _set_identity_session(user, normalized_email)


def _logout_current_user() -> None:
    try:
        logout_user()
    except Exception:
        LOG.debug("logout_user not available in current runtime")
    clear_identity_session()


def _build_reset_url(token: str, next_url: Optional[str], email: str) -> str:
    base = email_delivery.absolute_site_url("/login")
    params = {"auth": token, "email": email}
    if next_url:
        params["next"] = next_url
    return f"{base}?{urlencode(params)}"


def _reset_catalog_scope_to_all_if_no_next(next_raw: Optional[str]) -> None:
    """Ensure landing page shows all books when no explicit return URL exists.

    We reset when the login flow doesn't have a meaningful return URL.
    In practice, the login form may still submit a `next` value like `/`.
    If `next` points at a specific page (e.g. `/catalog/my-books`), we preserve
    the scope set by that flow.
    """
    raw = (str(next_raw).strip() if next_raw is not None else "")
    if raw:
        try:
            path = urlparse(raw).path
        except Exception:
            path = raw
        if path not in {"", "/", "/login"}:
            return
    try:
        from app.routes.overrides.catalog_access import CATALOG_SCOPE_SESSION_KEY, CatalogScope

        session[CATALOG_SCOPE_SESSION_KEY] = CatalogScope.ALL.value
        return
    except Exception:
        # Fallback: older session key name or if overrides cannot be imported.
        session["catalog_scope"] = "all"


def _remember_me_enabled(raw_value: Optional[str]) -> bool:
    if raw_value is None:
        return True
    lowered = raw_value.strip().lower()
    return lowered in {"1", "true", "yes", "on"}


def _apply_locale_from_auth_token(token_ctx: Optional[TokenDisplay], raw_token: Optional[str]) -> None:
    """Set session locale from the user referenced by the auth token.

    This is a best-effort UX improvement: it does not authenticate the token;
    it only uses the embedded email to pick a language for the login UI.
    """
    # If the visitor explicitly switched language (e.g. via the nav selector),
    # do not override their choice just because an auth token is present.
    try:
        from app.routes.language_switch import EXPLICIT_LOCALE_KEY

        if session.get(EXPLICIT_LOCALE_KEY):
            return
    except Exception:
        # Defensive: never fail the login flow due to a locale hint.
        pass

    candidate_email = token_ctx.email if token_ctx and token_ctx.email else None
    if not candidate_email:
        candidate_email = _extract_token_email(raw_token)
    token_email = normalize_email(candidate_email)
    if not token_email:
        return
    user = _fetch_user_by_email(token_email)
    if not user:
        return
    locale = normalize_language_choice(getattr(user, "locale", None))
    if locale:
        session[SESSION_LOCALE_KEY] = locale


def _send_reset_email(normalized_email: str, next_url: str) -> Optional[str]:
    user = calibre_users_service.lookup_user_by_email(normalized_email)
    if not user:
        LOG.info("password reset requested for missing account email=%s", normalized_email)
        return None
    try:
        token = password_reset_service.issue_reset_token(email=normalized_email)
    except password_reset_service.PasswordResetError as exc:
        LOG.warning("reset token issuance failed email=%s error=%s", normalized_email, exc)
        return _("Reset email failed. Try again.")
    reset_url = _build_reset_url(token, next_url, normalized_email)
    display_name = user.get("name") or user.get("email") or normalized_email
    preferred_language = user.get("locale") if isinstance(user, dict) else None
    try:
        email_delivery.send_password_reset_email(
            recipient_email=normalized_email,
            user_name=display_name,
            reset_url=reset_url,
            preferred_language=preferred_language,
        )
    except email_delivery.EmailDeliveryError as exc:
        LOG.warning("password reset email failed email=%s error=%s", normalized_email, exc)
        return _("Email service is unavailable. Try again.")
    LOG.info("password reset email queued email=%s", normalized_email)
    return None


def _handle_standard_login(
    *,
    email_value: str,
    password_value: str,
    remember_me: bool,
    next_url: str,
    token_ctx: Optional[TokenDisplay],
) -> Response | str:
    normalized = normalize_email(email_value)
    if not normalized:
        return _("Enter your email address.")
    if not password_value:
        return _("Enter your password.")
    if token_ctx and token_ctx.has_temp_password:
        return _("Set your new password first.")
    user = _authenticate_credentials(normalized, password_value)
    if not user:
        return _("Wrong email or password.")
    _perform_login(user, remember_me, normalized)
    flash(_("Signed in successfully."), "success")
    return redirect(next_url)


def _resolve_pending_reset(email_value: str, token: str) -> PendingReset:
    try:
        return password_reset_service.resolve_pending_reset(email=email_value, token=token)
    except password_reset_service.PendingResetNotFoundError as exc:
        raise ValueError("reset_not_found") from exc
    except password_reset_service.PasswordResetError as exc:
        raise ValueError(str(exc)) from exc


def _handle_password_update(
    *,
    email_value: str,
    token: str,
    new_password: str,
    confirm_password: str,
    remember_me: bool,
    next_url: str,
) -> Response | str:
    normalized = normalize_email(email_value)
    if not normalized:
        return _("Enter your email address.")
    if not new_password or not confirm_password:
        return _("Type and confirm your new password.")
    if new_password != confirm_password:
        return _("Passwords do not match.")
    try:
        _resolve_pending_reset(normalized, token)
    except ValueError as exc:
        LOG.warning("pending reset validation failed email=%s error=%s", normalized, exc)
        return _("Reset link is no longer valid.")
    try:
        password_reset_service.complete_password_change(email=normalized, new_password=new_password)
    except password_reset_service.PendingResetNotFoundError:
        return _("Couldn't update this account. Request a new link.")
    except getattr(password_reset_service, "PasswordPolicyError", Exception) as exc:
        # Avoid showing raw exception text (often English); render a translated message.
        LOG.info("password policy rejected email=%s detail=%s", normalized, str(exc).strip())
        return _("Password doesn't comply with password validation rules")
    except password_reset_service.PasswordResetError as exc:
        LOG.warning("password change failed email=%s error=%s", normalized, exc)
        return _("Password update failed. Try again.")
    user = _fetch_user_by_email(normalized)
    if not user:
        return _("Password updated. Please sign in again.")
    _perform_login(user, remember_me, normalized)
    flash(_("Password updated. You're signed in."), "success")
    return redirect(next_url)


@bp.route("/login", methods=["GET", "POST"])
def login_page():  # pragma: no cover - integration tested via Flask client
    next_raw = request.values.get("next")
    next_url = _sanitize_next(next_raw)
    auth_token = request.values.get("auth")
    token_ctx, token_error = _build_token_context(auth_token)

    # Prefer the token user's locale when rendering the login page.
    _apply_locale_from_auth_token(token_ctx, auth_token)

    if token_ctx and token_ctx.email:
        email_value = token_ctx.email
    else:
        email_value = request.values.get("email") or ""
    remember_me = _remember_me_enabled(request.form.get("remember_me")) if request.method == "POST" else True
    form_errors: List[str] = []

    if request.method == "GET":
        auto_redirect = _maybe_short_circuit_login(token_ctx, next_url, auth_token)
        if auto_redirect is not None:
            return auto_redirect

    if request.method == "POST":
        action = request.form.get("action") or "login"
        if action == "forgot":
            normalized = normalize_email(email_value)
            if not normalized:
                form_errors.append(_("Enter your email address."))
            else:
                error = _send_reset_email(normalized, next_url)
                if error:
                    form_errors.append(error)
                else:
                    flash(_("Reset instructions sent to your email."), "info")
                    return redirect(url_for("login_override.login_page", next=next_url))
        elif auth_token and (action == "complete_reset" or (token_ctx and token_ctx.has_temp_password)):
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            result = _handle_password_update(
                email_value=email_value,
                token=auth_token,
                new_password=new_password,
                confirm_password=confirm_password,
                remember_me=remember_me,
                next_url=next_url,
            )
            if isinstance(result, Response):
                _reset_catalog_scope_to_all_if_no_next(next_raw)
                return result
            form_errors.append(result)
        else:
            result = _handle_standard_login(
                email_value=email_value,
                password_value=request.form.get("password", ""),
                remember_me=remember_me,
                next_url=next_url,
                token_ctx=token_ctx,
            )
            if isinstance(result, Response):
                _reset_catalog_scope_to_all_if_no_next(next_raw)
                return result
            form_errors.append(result)

    context = {
        "next_url": next_url,
        "email_value": email_value,
        "remember_me": remember_me,
        "auth_token": auth_token,
        "token_context": token_ctx,
        "token_error": token_error,
        "form_errors": form_errors,
        "csrf_token_value": generate_csrf(),
    }
    # Match upstream Calibre-Web templates: they expect `config` to be the
    # ConfigSQL instance (not Flask's app.config mapping).
    if cw_config is not None:
        context["config"] = cw_config
    # Use Calibre-Web's rendering helper to ensure template variables like
    # `instance` and `sidebar` are present (keeps /login consistent with /).
    if _cw_render_title_template:
        return _cw_render_title_template("login_override.html", **context)
    return render_template("login_override.html", **context)


def register_login_override(app: Any) -> None:  # pragma: no cover - glue code
    if getattr(app, "_users_books_login_override", False):  # type: ignore[attr-defined]
        return
    app.register_blueprint(bp)
    _map_calibre_login_endpoints(app)
    setattr(app, "_users_books_login_override", True)
    LOG.debug("Login override blueprint registered")


def _map_calibre_login_endpoints(app: Any) -> None:
    """Remap core Calibre-Web /login endpoints to our override view."""

    override_endpoint = "login_override.login_page"
    override_view = app.view_functions.get(override_endpoint)
    if not override_view:
        LOG.warning("Login override view missing; Calibre endpoints not updated")
        return
    for endpoint in ("web.login", "web.login_post"):
        if endpoint in app.view_functions:
            app.view_functions[endpoint] = override_view
            LOG.debug("Login override mapped endpoint %s", endpoint)


__all__ = ["register_login_override", "bp"]