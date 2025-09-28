"""Application logging helpers (internal).

Implements a lightweight singleton logger similar to the prior plugin
`logging_setup` so we can drop the plugin dependency. Honors the log
level from `app.config.log_level_name()`.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from app import config as app_config

_LOCK = threading.Lock()
_PRIMARY: Optional[logging.Logger] = None


def get_logger(name: str = "app") -> logging.Logger:
    global _PRIMARY
    if name == "app" and _PRIMARY is not None:
        return _PRIMARY
    with _LOCK:
        if name == "app" and _PRIMARY is not None:
            return _PRIMARY
        logger = logging.getLogger(name)
        level_name = app_config.log_level_name()
        level = getattr(logging, level_name, logging.INFO)
        logger.setLevel(level)
        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("[app] %(asctime)s %(levelname)s %(name)s %(message)s"))
            logger.addHandler(handler)
        logger.propagate = False
        if name == "app":
            _PRIMARY = logger
        return logger


__all__ = ["get_logger"]
