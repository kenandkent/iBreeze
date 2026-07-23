"""Structured logging configuration."""
import logging
import sys
from typing import Any


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Setup structured logging."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    if json_format:
        # TODO: Add structlog or JSON formatter
        logging.basicConfig(
            level=log_level,
            format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}',
            stream=sys.stdout,
        )
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
        )


def get_logger(name: str) -> logging.Logger:
    """Get a named logger."""
    return logging.getLogger(name)
