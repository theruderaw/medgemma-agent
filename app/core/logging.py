"""Structured logging setup.

The whole app logs through structlog. Every log line is emitted twice:

- to the console, rendered human-readably (``structlog.dev.ConsoleRenderer``),
- to ``app/logs/app.jsonl`` as one JSON object per line (rotating,
  5 MB x 3 backups) for machines and audit-oriented tooling.

Uvicorn and Celery loggers are routed through the same stdlib formatter so
framework noise lands alongside app logs as structured records. Context
variables (``session_id``, ``turn_id``, ``job_id``, ...) are merged into every
line via ``structlog.contextvars``.

Idempotent, so it is safe to call from both the API and worker entrypoints.
"""

import logging
import logging.handlers
from pathlib import Path

import structlog

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
JSON_LOG_FILENAME = "app.jsonl"

_configured = False
_handlers: tuple[logging.Handler, logging.Handler] | None = None

_PROCESSORS: list = [
    structlog.contextvars.merge_contextvars,
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.stdlib.add_logger_name,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]


def _configure_structlog() -> None:
    """Point structlog at stdlib logging, buffering event dicts for formatters."""
    structlog.configure(
        processors=[
            *_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _formatter(renderer: structlog.typing.Processor) -> structlog.stdlib.ProcessorFormatter:
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
    )


def _file_handler() -> logging.handlers.RotatingFileHandler:
    handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / JSON_LOG_FILENAME,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(_formatter(structlog.processors.JSONRenderer(ensure_ascii=False)))
    return handler


def _console_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler()
    handler.setFormatter(_formatter(structlog.dev.ConsoleRenderer()))
    return handler


def _get_handlers() -> tuple[logging.Handler, logging.Handler]:
    """Return the shared console + JSONL handlers (created once)."""
    global _handlers
    if _handlers is None:
        _handlers = (_console_handler(), _file_handler())
    return _handlers


def setup_logging() -> None:
    """Configure root, uvicorn, and celery loggers for structured output."""
    global _configured

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _configure_structlog()

    root = logging.getLogger()
    if not _configured:
        root.setLevel(logging.INFO)
        for handler in _get_handlers():
            root.addHandler(handler)
        _configured = True

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "celery", "celery.task"):
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        for handler in _get_handlers():
            logger.addHandler(handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger with the current context merged in."""
    return structlog.get_logger(name)