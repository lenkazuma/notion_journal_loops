"""
Step 3: Generate embeddings for all chunks.
Output: data/embeddings/embeddings.pkl + data/embeddings/chunk_ids.json
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.config import CHUNKS_DIR, EMBEDDINGS_DIR
from src.llm.embedder import embed_chunks, get_provider
from src.utils.logger import get_logger

logger = get_logger("pipeline.step3")


def run(
    chunks: Optional[List[Dict]] = None,
    provider_name: Optional[str] = None,
    force: bool = False,
) -> Tuple[np.ndarray, List[str]]:
    """
    Generate embeddings for all chunks.

    Parameters
    ----------
    chunks : list of chunk dicts (loaded from cache if None)
    provider_name : override LLM provider
    force : re-embed even if cache exists

    Returns
    -------
    (embeddings_matrix, chunk_ids)
    """
    logger.info("=" * 60)
    logger.info("STEP 3: Generating embeddings")
    logger.info("=" * 60)

    if chunks is None:
        chunks_cache = CHUNKS_DIR / "chunks.json"
        if not chunks_cache.exists():
            raise FileNotFoundError(
                "No chunks cache found. Run step 2 first."
            )
        chunks = json.loads(chunks_cache.read_text(encoding="utf-8"))

    logger.info(f"Embedding {len(chunks)} chunks...")

    provider = get_provider(provider_name)
    embeddings, chunk_ids = embed_chunks(chunks, provider=provider, force=force)

    logger.info(f"Step 3 complete: embeddings shape {embeddings.shape}")
    return embeddings, chunk_ids
