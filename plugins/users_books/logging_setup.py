"""
Logging setup for the users_books plugin.

Responsibilities:
  - Centralized creation of the plugin logger.
  - Honor dynamic log level from configuration (environment-driven).
  - Provide helpers for temporarily changing log level and decorating functions
    for exception logging.
  - Avoid duplicate handlers if init_app() / tests import multiple times.

Usage:
    from .logging_setup import get_logger, refresh_level
    log = get_logger()
    log.info("Something")

Changing Log Level at Runtime:
    # Update USERS_BOOKS_LOG_LEVEL env var externally, then call:
    refresh_level()

Testing:
    - Mocks can patch config.log_level_name() before first call to get_logger().
    - temp_level() context manager is handy to force DEBUG verbosity inside a test.

Design Notes:
  - We do not automatically replace existing handlers for safety—if you want to
    redirect logs, clear handlers manually before calling get_logger().
  - Logger propagation is disabled to prevent double logging if the application
    root logger is also configured.

"""

from __future__ import annotations

import logging
import threading
import contextlib
from typing import Callable, TypeVar, Any, Optional

from . import config

_LOGGER: Optional[logging.Logger] = None
_LOCK = threading.Lock()

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Core logger access
# ---------------------------------------------------------------------------

def get_logger(name: str = "users_books") -> logging.Logger:
    """
    Return the singleton plugin logger (default name 'users_books').

    If a different name is requested, it is configured similarly but not cached
    as the global singleton (used rarely for sub-modules).
    """
    global _LOGGER
    if name == "users_books" and _LOGGER is not None:
        return _LOGGER

    with _LOCK:
        if name == "users_books" and _LOGGER is not None:
            return _LOGGER

        logger = logging.getLogger(name)
        level_name = config.log_level_name()
        level = getattr(logging, level_name, logging.INFO)
        logger.setLevel(level)

        # Attach a single StreamHandler if none exists.
        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            handler = logging.StreamHandler()
            fmt = "[users_books] %(asctime)s %(levelname)s %(name)s %(message)s"
            handler.setFormatter(logging.Formatter(fmt))
            logger.addHandler(handler)

        # Prevent messages from bubbling to root if root also configured
        logger.propagate = False

        if name == "users_books":
            _LOGGER = logger
        return logger


# ---------------------------------------------------------------------------
# Dynamic level management
# ---------------------------------------------------------------------------

def refresh_level() -> int:
    """
    Re-read log level from configuration and apply if changed.
    Returns the effective (possibly updated) level.
    """
    logger = get_logger()
    new_level_name = config.log_level_name()
    new_level = getattr(logging, new_level_name, logging.INFO)
    if logger.level != new_level:
        old = logging.getLevelName(logger.level)
        logger.setLevel(new_level)
        logger.info("Log level changed from %s to %s", old, new_level_name)
    return logger.level


@contextlib.contextmanager
def temp_level(level: int):
    """
    Temporarily set the plugin logger to a specific level inside a context.

    Example:
        with temp_level(logging.DEBUG):
            log.debug("Verbose details")
    """
    logger = get_logger()
    old = logger.level
    logger.setLevel(level)
    try:
        yield logger
    finally:
        logger.setLevel(old)


# ---------------------------------------------------------------------------
# Exception logging decorator
# ---------------------------------------------------------------------------

def log_exceptions(
    *,
    reraise: bool = True,
    level: int = logging.ERROR,
    message: str = "Unhandled exception"
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to log exceptions raised by the wrapped function.

    Parameters:
      reraise: If True (default), exception is re-raised after logging.
      level:   Logging level used for the exception record.
      message: Base message prefix.

    Usage:
        @log_exceptions(message="Processing user filter")
        def do_work(...):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            log = get_logger()
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                log.log(level, "%s: %s", message, exc, exc_info=True)
                if reraise:
                    raise
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "get_logger",
    "refresh_level",
    "temp_level",
    "log_exceptions",
]
