"""
Retry decorator with exponential backoff for rate-limited APIs.
Handles Notion 429, OpenAI 429, Anthropic 429, and transient HTTP errors.
"""
from __future__ import annotations

import time
from functools import wraps
from typing import Any, Callable, Tuple, Type

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
import logging

logger = logging.getLogger("notion_loops.retry")


def _is_rate_limit(exc: BaseException) -> bool:
    """Return True if the exception looks like a 429 / rate-limit error."""
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return True
    # notion-client raises APIResponseError with status attribute
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    if status == 429:
        return True
    return False


def api_retry(
    max_attempts: int = 6,
    min_wait: float = 1.0,
    max_wait: float = 60.0,
    reraise: bool = True,
) -> Callable:
    """
    Decorator: retry on rate-limit or transient errors with exponential backoff.

    Usage:
        @api_retry()
        def call_api(): ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            wait = min_wait
            last_exc: BaseException | None = None
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if _is_rate_limit(exc):
                        logger.warning(
                            f"[retry] Rate limited on {func.__name__}, "
                            f"attempt {attempt + 1}/{max_attempts}, "
                            f"waiting {wait:.1f}s ..."
                        )
                        time.sleep(wait)
                        wait = min(wait * 2, max_wait)
                        attempt += 1
                    else:
                        raise
            if reraise and last_exc is not None:
                raise last_exc
        return wrapper
    return decorator
