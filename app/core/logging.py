"""Application logging setup.

All logs are written to `app/logs/app.log` (rotating, 5 MB x 3 backups) in
addition to the console. Uvicorn and Celery loggers are wired to the same file
handler so framework noise lands alongside app logs. Idempotent, so it is safe
to call from both the API and worker entrypoints.
"""

import logging
import logging.handlers
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILENAME = "app.log"
_LOG_FILE_HANDLER_ATTR = "_medgemma_file_handler"

_configured = False


def _formatter() -> logging.Formatter:
    return logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")


def _file_handler() -> logging.handlers.RotatingFileHandler:
    handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / LOG_FILENAME,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(_formatter())
    return handler


def _attach_file_handler(logger: logging.Logger) -> None:
    for existing in logger.handlers:
        if getattr(existing, _LOG_FILE_HANDLER_ATTR, False):
            return
    handler = _file_handler()
    setattr(handler, _LOG_FILE_HANDLER_ATTR, True)
    logger.addHandler(handler)


def setup_logging() -> None:
    """Configure root, uvicorn, and celery loggers to write into app/logs."""
    global _configured

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if not _configured:
        root.setLevel(logging.INFO)
        console = logging.StreamHandler()
        console.setFormatter(_formatter())
        root.addHandler(console)
        root.addHandler(_file_handler())
        _configured = True

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.task"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _attach_file_handler(logger)