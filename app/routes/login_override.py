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
from urllib.parse import urlencode

from app.services import auth_link_service, password_reset_service, email_delivery, calibre_users_service
from app.services.password_reset_service import PendingReset
from app.utils.identity import clear_identity_session, get_current_user_email, get_session_email_key, normalize_email
from app.utils.logging import get_logger

LOG = get_logger("login_override")
bp = Blueprint("login_override", __name__)


@dataclass(frozen=True)
class TokenDisplay:
    token: str
    email: Optional[str]
    has_temp_password: bool
    issued_at: Optional[str]


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
        return None, str(exc)
    return TokenDisplay(
        token=token,
        email=payload.get("email"),
        has_temp_password=bool(payload.get("temp_password")),
        issued_at=payload.get("issued_at"),
    ), None


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


def _maybe_short_circuit_login(token_ctx: Optional[TokenDisplay], next_url: str) -> Optional[Response]:
    if not token_ctx or not token_ctx.email or not next_url:
        return None
    token_email = normalize_email(token_ctx.email)
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


def _remember_me_enabled(raw_value: Optional[str]) -> bool:
    if raw_value is None:
        return True
    lowered = raw_value.strip().lower()
    return lowered in {"1", "true", "yes", "on"}


def _send_reset_email(normalized_email: str, next_url: str) -> Optional[str]:
    user = calibre_users_service.lookup_user_by_email(normalized_email)
    if not user:
        LOG.info("password reset requested for missing account email=%s", normalized_email)
        return None
    try:
        token = password_reset_service.issue_reset_token(email=normalized_email)
    except password_reset_service.PasswordResetError as exc:
        LOG.warning("reset token issuance failed email=%s error=%s", normalized_email, exc)
        return "Reset email failed. Try again."
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
        return "Email service is unavailable. Try again."
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
        return "Enter your email address."
    if not password_value:
        return "Enter your password."
    if token_ctx and token_ctx.has_temp_password:
        return "Set your new password first."
    user = _authenticate_credentials(normalized, password_value)
    if not user:
        return "Wrong email or password."
    _perform_login(user, remember_me, normalized)
    flash("Signed in successfully.", "success")
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
        return "Enter your email address."
    if not new_password or not confirm_password:
        return "Type and confirm your new password."
    if new_password != confirm_password:
        return "Passwords do not match."
    try:
        _resolve_pending_reset(normalized, token)
    except ValueError as exc:
        LOG.warning("pending reset validation failed email=%s error=%s", normalized, exc)
        return "Reset link is no longer valid."
    try:
        password_reset_service.complete_password_change(email=normalized, new_password=new_password)
    except password_reset_service.PendingResetNotFoundError:
        return "Couldn't update this account. Request a new link."
    except password_reset_service.PasswordResetError as exc:
        LOG.warning("password change failed email=%s error=%s", normalized, exc)
        return "Password update failed. Try again."
    user = _fetch_user_by_email(normalized)
    if not user:
        return "Password updated. Please sign in again."
    _perform_login(user, remember_me, normalized)
    flash("Password updated. You're signed in.", "success")
    return redirect(next_url)


@bp.route("/login", methods=["GET", "POST"])
def login_page():  # pragma: no cover - integration tested via Flask client
    next_raw = request.values.get("next")
    next_url = _sanitize_next(next_raw)
    auth_token = request.values.get("auth")
    token_ctx, token_error = _build_token_context(auth_token)
    if token_ctx and token_ctx.email:
        email_value = token_ctx.email
    else:
        email_value = request.values.get("email") or ""
    remember_me = _remember_me_enabled(request.form.get("remember_me")) if request.method == "POST" else True
    form_errors: List[str] = []

    if request.method == "GET":
        auto_redirect = _maybe_short_circuit_login(token_ctx, next_url)
        if auto_redirect is not None:
            return auto_redirect

    if request.method == "POST":
        action = request.form.get("action") or "login"
        if action == "forgot":
            normalized = normalize_email(email_value)
            if not normalized:
                form_errors.append("Enter your email address.")
            else:
                error = _send_reset_email(normalized, next_url)
                if error:
                    form_errors.append(error)
                else:
                    flash("Reset instructions sent to your email.", "info")
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