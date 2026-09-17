"""
Structured logging, configured once and shared by both the FastAPI
process and Celery workers. JSON output so a worker failure is
diagnosable from logs alone — job_id, event_id, channel, attempt,
provider, status, duration_ms, error are the fields that matter (see
app/workers/tasks.py for where they're populated).
"""

import logging

import structlog

from app.core.config import get_settings

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    settings = get_settings()
    logging.basicConfig(format="%(message)s", level=settings.log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            # Renders exc_info=True into a plain "exception" string field
            # BEFORE JSONRenderer runs. Without this, passing exc_info=True
            # to a log call would hand JSONRenderer a raw (type, value,
            # traceback) tuple, which isn't JSON-serializable -- the log
            # call itself would fail exactly when it matters most: while
            # handling an unexpected exception (see
            # app/main.py's unhandled_exception_handler).
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True
