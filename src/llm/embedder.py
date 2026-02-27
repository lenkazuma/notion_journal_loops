"""
Embedding orchestrator.
Handles batch embedding, caching to disk, and provider fallback.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from src.config import EMBEDDINGS_DIR
from src.llm.provider_base import ProviderBase
from src.utils.logger import get_logger

logger = get_logger("llm.embedder")

EMBEDDINGS_CACHE = EMBEDDINGS_DIR / "embeddings.pkl"
CHUNK_IDS_CACHE = EMBEDDINGS_DIR / "chunk_ids.json"


def get_provider(provider_name: Optional[str] = None) -> ProviderBase:
    """
    Factory: return the appropriate provider based on config or argument.
    Falls back gracefully if the requested provider is unavailable.
    """
    from src.config import LLM_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY

    name = provider_name or LLM_PROVIDER

    if name == "openai":
        if not OPENAI_API_KEY:
            logger.warning("LLM_PROVIDER=openai but OPENAI_API_KEY not set. Using fallback.")
            from src.llm.provider_fallback import ProviderFallback
            return ProviderFallback()
        from src.llm.provider_openai import ProviderOpenAI
        return ProviderOpenAI()

    elif name == "anthropic":
        if not ANTHROPIC_API_KEY:
            logger.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY not set. Using fallback.")
            from src.llm.provider_fallback import ProviderFallback
            return ProviderFallback()
        from src.llm.provider_anthropic import ProviderAnthropic
        return ProviderAnthropic()

    else:
        from src.llm.provider_fallback import ProviderFallback
        return ProviderFallback()


def embed_chunks(
    chunks: List[Dict],
    provider: Optional[ProviderBase] = None,
    force: bool = False,
) -> tuple[np.ndarray, List[str]]:
    """
    Generate embeddings for all chunks.

    Parameters
    ----------
    chunks : list of chunk dicts (must have 'chunk_id' and 'text')
    provider : LLM provider (auto-detected if None)
    force : re-embed even if cache exists

    Returns
    -------
    (embeddings_matrix, chunk_ids)
    embeddings_matrix: shape (N, D) numpy array
    chunk_ids: list of chunk_id strings in same order
    """
    if not force and EMBEDDINGS_CACHE.exists() and CHUNK_IDS_CACHE.exists():
        logger.info("Loading embeddings from cache...")
        embeddings = pickle.loads(EMBEDDINGS_CACHE.read_bytes())
        chunk_ids = json.loads(CHUNK_IDS_CACHE.read_text(encoding="utf-8"))
        logger.info(f"Loaded {len(chunk_ids)} embeddings from cache.")
        return embeddings, chunk_ids

    if provider is None:
        provider = get_provider()

    logger.info(f"Generating embeddings using provider: {provider.name}")

    texts = [c["text"] for c in chunks]
    chunk_ids = [c["chunk_id"] for c in chunks]

    if not provider.supports_embedding:
        logger.warning(
            f"Provider '{provider.name}' does not support embeddings. "
            "Falling back to TF-IDF."
        )
        from src.llm.provider_fallback import ProviderFallback
        fallback = ProviderFallback()
        raw_embeddings = fallback.embed(texts)
    else:
        try:
            raw_embeddings = provider.embed(texts)
        except NotImplementedError:
            logger.warning("Provider raised NotImplementedError for embed(). Using TF-IDF fallback.")
            from src.llm.provider_fallback import ProviderFallback
            fallback = ProviderFallback()
            raw_embeddings = fallback.embed(texts)

    embeddings = np.array(raw_embeddings, dtype=np.float32)
    logger.info(f"Generated embeddings: shape {embeddings.shape}")

    # Cache to disk
    EMBEDDINGS_CACHE.write_bytes(pickle.dumps(embeddings))
    CHUNK_IDS_CACHE.write_text(
        json.dumps(chunk_ids, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info(f"Saved embeddings to {EMBEDDINGS_CACHE}")

    return embeddings, chunk_ids
