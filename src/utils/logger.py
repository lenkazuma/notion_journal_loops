"""
Centralized logger using Python's logging + rich handler.
"""
from __future__ import annotations

import logging
import sys

from rich.logging import RichHandler


def get_logger(name: str = "notion_loops") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    from src.config import LOG_LEVEL

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(level)

    handler = RichHandler(
        rich_tracebacks=True,
        show_time=True,
        show_path=False,
        markup=True,
    )
    handler.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    return logger
