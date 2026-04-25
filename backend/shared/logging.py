"""Shared logging configuration."""

from __future__ import annotations

import logging

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(log_level: str = "INFO") -> None:
    """Configure process-wide logging for API and service modules."""
    resolved_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(level=resolved_level, format=LOG_FORMAT, force=True)
    logging.getLogger("uvicorn.access").setLevel(resolved_level)
    logging.getLogger(__name__).info(
        "logging_configured | level=%s",
        logging.getLevelName(resolved_level),
    )
