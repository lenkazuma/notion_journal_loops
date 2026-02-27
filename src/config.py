"""
Central configuration loader.
Reads from .env (or environment variables) and exposes typed settings.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env from project root (two levels up from this file)
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _get_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _get_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, str(default)).strip().lower()
    return val in ("1", "true", "yes", "on")


# ── Notion ──────────────────────────────────────────────────────────────────
NOTION_TOKEN: str = _get("NOTION_TOKEN")
NOTION_DATABASE_ID: str = _get("NOTION_DATABASE_ID")
NOTION_TITLE_PROPERTY: str = _get("NOTION_TITLE_PROPERTY", "Name")
NOTION_DATE_PROPERTY: str = _get("NOTION_DATE_PROPERTY", "Formulated Date")

# ── LLM Provider ────────────────────────────────────────────────────────────
LLM_PROVIDER: Literal["openai", "anthropic", "fallback"] = _get("LLM_PROVIDER", "openai")  # type: ignore[assignment]
OPENAI_API_KEY: str = _get("OPENAI_API_KEY")
ANTHROPIC_API_KEY: str = _get("ANTHROPIC_API_KEY")

# ── Models ───────────────────────────────────────────────────────────────────
OPENAI_EMBED_MODEL: str = _get("OPENAI_EMBED_MODEL", "text-embedding-3-small")
OPENAI_CHAT_MODEL: str = _get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
ANTHROPIC_CHAT_MODEL: str = _get("ANTHROPIC_CHAT_MODEL", "claude-3-haiku-20240307")

# ── Chunking ─────────────────────────────────────────────────────────────────
CHUNK_TARGET_TOKENS: int = _get_int("CHUNK_TARGET_TOKENS", 700)
CHUNK_MAX_TOKENS: int = _get_int("CHUNK_MAX_TOKENS", 900)

# ── Clustering ───────────────────────────────────────────────────────────────
CLUSTER_METHOD: Literal["hdbscan", "kmeans"] = _get("CLUSTER_METHOD", "hdbscan")  # type: ignore[assignment]
HDBSCAN_MIN_CLUSTER_SIZE: int = _get_int("HDBSCAN_MIN_CLUSTER_SIZE", 8)
KMEANS_K_MIN: int = _get_int("KMEANS_K_MIN", 3)
KMEANS_K_MAX: int = _get_int("KMEANS_K_MAX", 20)

# ── Summarization ────────────────────────────────────────────────────────────
SUMMARY_SAMPLE_PER_CLUSTER: int = _get_int("SUMMARY_SAMPLE_PER_CLUSTER", 30)

# ── Deduplication ────────────────────────────────────────────────────────────
DUP_SIM_THRESHOLD: float = _get_float("DUP_SIM_THRESHOLD", 0.92)
DUP_CROSS_CLUSTER: bool = _get_bool("DUP_CROSS_CLUSTER", False)

# ── Writeback ────────────────────────────────────────────────────────────────
WRITEBACK_MODE: Literal["off", "dryrun", "on"] = _get("WRITEBACK_MODE", "off")  # type: ignore[assignment]

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT: Path = _PROJECT_ROOT
DATA_DIR: Path = _PROJECT_ROOT / _get("CACHE_DIR", "data")
RAW_DIR: Path = DATA_DIR / "raw"
CHUNKS_DIR: Path = DATA_DIR / "chunks"
EMBEDDINGS_DIR: Path = DATA_DIR / "embeddings"
CLUSTERS_DIR: Path = DATA_DIR / "clusters"
OUTPUTS_DIR: Path = DATA_DIR / "outputs"

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = _get("LOG_LEVEL", "INFO").upper()

# Ensure data directories exist
for _d in (RAW_DIR, CHUNKS_DIR, EMBEDDINGS_DIR, CLUSTERS_DIR, OUTPUTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def validate() -> None:
    """Raise ValueError if critical config is missing."""
    if not NOTION_TOKEN:
        raise ValueError("NOTION_TOKEN is not set. Check your .env file.")
    if not NOTION_DATABASE_ID:
        raise ValueError("NOTION_DATABASE_ID is not set. Check your .env file.")
    if LLM_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise ValueError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set.")
    if LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        raise ValueError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set.")
