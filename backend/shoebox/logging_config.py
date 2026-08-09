"""Logging setup.

One call, made from the app factory. Logs go to stderr *and* to a
rotating file under ``<data_dir>/logs/shoebox.log`` so that a failed
upload at 11pm is still diagnosable the next morning — the HTTP response
body is not a log.

Level is ``SHOEBOX_LOG_LEVEL`` (default ``INFO``). File logging can be
switched off with ``SHOEBOX_LOG_TO_FILE=false``.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from shoebox.config import get_settings

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
_configured = False


def configure_logging() -> None:
    """Idempotently attach shoebox's handlers to the root logger."""
    global _configured
    if _configured:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    if settings.log_to_file:
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Pillow and urllib3 are chatty at DEBUG and say nothing useful.
    logging.getLogger("PIL").setLevel(logging.INFO)

    _configured = True
    logging.getLogger("shoebox").info(
        "Logging configured: level=%s file=%s",
        settings.log_level.upper(),
        settings.log_path if settings.log_to_file else "disabled",
    )


def reset_logging() -> None:
    """Test hook: drop handlers so the next configure call re-runs."""
    global _configured
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    _configured = False
