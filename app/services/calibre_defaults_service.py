"""Apply opinionated Calibre-Web defaults for ebooks.lv.

This module intentionally interacts with Calibre-Web runtime objects (cps.config)
via lazy imports so it can be imported safely in non-Calibre contexts.
"""

from __future__ import annotations

from typing import Any, Dict

from app.config import app_title


class CalibreRuntimeUnavailable(RuntimeError):
    pass


def apply_ebookslv_default_settings() -> Dict[str, Any]:
    """Apply curated defaults matching the ebooks.lv production configuration.

    Notes:
    - Does NOT touch:
      - Allowed Upload Fileformats
      - Regular Expression for Title Sorting
    """
    try:
        from cps import config as cw_config  # type: ignore
        from cps import constants as cw_constants  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise CalibreRuntimeUnavailable("calibre_runtime_unavailable") from exc

    desired_roles = int(cw_constants.ROLE_VIEWER | cw_constants.ROLE_PASSWD)
    desired_visibility = int(
        cw_constants.SIDEBAR_READ_AND_UNREAD
        | cw_constants.SIDEBAR_CATEGORY
        | cw_constants.SIDEBAR_SERIES
        | cw_constants.SIDEBAR_AUTHOR
        | cw_constants.SIDEBAR_LANGUAGE
        | cw_constants.SIDEBAR_FORMAT
        | cw_constants.SIDEBAR_ARCHIVED
        | cw_constants.SIDEBAR_LIST
    )

    title_value = app_title() or "e-books.lv"

    # UI Configuration
    cw_config.config_calibre_web_title = title_value
    cw_config.config_books_per_page = 60
    cw_config.config_random_books = 4
    cw_config.config_authors_max = 0

    # Default Settings for New Users
    cw_config.config_default_role = desired_roles
    cw_config.config_default_show = desired_visibility
    cw_config.config_default_locale = "lv"
    cw_config.config_default_language = "all"

    # Feature Configuration
    cw_config.config_embed_metadata = True
    cw_config.config_uploading = 1
    cw_config.config_anonbrowse = 1
    cw_config.config_public_reg = 0
    cw_config.config_remote_login = False
    cw_config.config_allow_reverse_proxy_header_login = False
    # Keep reverse-proxy header name empty when disabled
    cw_config.config_reverse_proxy_login_header_name = ""
    # "Convert non-English characters..." should be unchecked.
    cw_config.config_unicode_filename = False

    # Security Settings
    cw_config.config_ratelimiter = True
    cw_config.config_limiter_uri = ""
    cw_config.config_limiter_options = ""
    cw_config.config_check_extensions = True
    # Session protection: template maps Strong -> 1
    cw_config.config_session = 1

    # Password policy
    cw_config.config_password_policy = True
    cw_config.config_password_min_length = 8
    cw_config.config_password_number = True
    cw_config.config_password_lower = True
    cw_config.config_password_upper = True
    cw_config.config_password_character = False
    cw_config.config_password_special = False

    cw_config.save()

    return {
        "title": cw_config.config_calibre_web_title,
        "books_per_page": cw_config.config_books_per_page,
        "random_books": cw_config.config_random_books,
        "authors_max": cw_config.config_authors_max,
        "roles_mask": desired_roles,
        "visibility_mask": desired_visibility,
        "default_locale": cw_config.config_default_locale,
        "default_language": cw_config.config_default_language,
        "embed_metadata": bool(cw_config.config_embed_metadata),
        "upload_enabled": bool(cw_config.config_uploading),
        "anonymous_browsing": bool(cw_config.config_anonbrowse),
        "public_registration": bool(cw_config.config_public_reg),
        "remote_login": bool(cw_config.config_remote_login),
        "reverse_proxy_auth": bool(getattr(cw_config, "config_allow_reverse_proxy_header_login", False)),
        "unicode_filename": bool(getattr(cw_config, "config_unicode_filename", False)),
        "ratelimiter": bool(cw_config.config_ratelimiter),
        "limiter_uri": cw_config.config_limiter_uri,
        "limiter_options": cw_config.config_limiter_options,
        "check_extensions": bool(cw_config.config_check_extensions),
        "session_protection": cw_config.config_session,
        "password_policy": bool(cw_config.config_password_policy),
        "password_min_length": cw_config.config_password_min_length,
        "password_number": bool(cw_config.config_password_number),
        "password_lower": bool(cw_config.config_password_lower),
        "password_upper": bool(cw_config.config_password_upper),
        "password_character": bool(cw_config.config_password_character),
        "password_special": bool(cw_config.config_password_special),
    }
