"""
Logging utilities for NestQuant.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional


def setup_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Set up a logger with console and optional file output.

    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path for log output

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    # Set level
    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logger.setLevel(log_level)

    # Clear existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
