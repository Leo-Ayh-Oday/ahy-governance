"""
Structured logging configuration using structlog.

Produces JSON lines to stdout for easy ingestion by log aggregators
(Loki, Elasticsearch, Datadog, etc.). Falls back to standard logging
if structlog is not installed.

Usage:
    from ahy_governance.logging_config import setup_logging, get_logger
    setup_logging(level="INFO")
    logger = get_logger(__name__)
    logger.info("agent_heartbeat", agent="Planner", latency_ms=120)
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from contextvars import ContextVar

# Correlation ID for request tracing across async boundaries
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    cid = _correlation_id.get()
    if not cid:
        cid = uuid.uuid4().hex[:12]
        _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    _correlation_id.set(cid)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging. Call once at startup."""
    lvl = getattr(logging, level.upper(), logging.INFO)

    try:
        import structlog

        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.dev.ConsoleRenderer()
                if os.environ.get("LOG_FORMAT") == "console"
                else structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

        # Set root logger level
        logging.basicConfig(format="%(message)s", stream=sys.stdout, level=lvl)
        # Quiet noisy third-party loggers
        for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    except ImportError:
        # structlog not installed — use standard logging with JSON format
        logging.basicConfig(
            format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
            stream=sys.stdout,
            level=lvl,
        )


def get_logger(name: str):
    """Get a structured logger for the given module name."""
    try:
        import structlog
        return structlog.get_logger(name)
    except ImportError:
        return logging.getLogger(name)
