"""
Token estimation utilities.
Uses tiktoken when available; falls back to character-based approximation.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

_tiktoken_available = False
try:
    import tiktoken
    _tiktoken_available = True
except ImportError:
    pass


@lru_cache(maxsize=4)
def _get_encoding(model: str = "cl100k_base"):
    if not _tiktoken_available:
        return None
    try:
        import tiktoken
        return tiktoken.get_encoding(model)
    except Exception:
        return None


def estimate_tokens(text: str, model: str = "cl100k_base") -> int:
    """
    Estimate token count for text.
    Uses tiktoken if available, otherwise approximates as len(text) / 3.5
    (works reasonably for mixed Chinese/English).
    """
    enc = _get_encoding(model)
    if enc is not None:
        return len(enc.encode(text))
    # Fallback: Chinese chars ≈ 1 token each, English words ≈ 1.3 tokens
    # Simple approximation: total_chars / 2.5 for mixed content
    return max(1, int(len(text) / 2.5))
