"""
Fallback provider: no API key required.
- Embeddings: TF-IDF vectors (scikit-learn)
- Chat/Summarization: returns a placeholder template (no LLM call)

This allows the pipeline to run steps 1-4 (fetch, chunk, embed, cluster)
without any API key. Summaries will be template-based, not AI-generated.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from src.llm.provider_base import ProviderBase
from src.utils.logger import get_logger

logger = get_logger("llm.fallback")


class ProviderFallback(ProviderBase):
    """
    No-API fallback provider.
    Uses TF-IDF for embeddings and template strings for summaries.
    """

    def __init__(self) -> None:
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._fitted_texts: List[str] = []

    @property
    def name(self) -> str:
        return "fallback"

    @property
    def supports_embedding(self) -> bool:
        return True  # TF-IDF is always available

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate TF-IDF vectors for texts.
        Note: TF-IDF vectors are corpus-dependent. For best results,
        fit on all texts at once. If called incrementally, re-fits each time.

        WARNING: TF-IDF similarity is less accurate than neural embeddings.
        Clustering and deduplication results will be lower quality.
        """
        if not texts:
            return []

        logger.warning(
            "Using TF-IDF fallback embeddings. "
            "Quality is significantly lower than neural embeddings. "
            "Set LLM_PROVIDER=openai and OPENAI_API_KEY for better results."
        )

        # Fit on all provided texts
        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            max_features=2048,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)
        dense = matrix.toarray()

        # L2-normalize for cosine similarity compatibility
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-10, norms)
        normalized = dense / norms

        return normalized.tolist()

    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """
        Return a template-based summary (no LLM call).
        Extracts the last user message and returns a structured placeholder.
        """
        user_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_content = msg["content"][:200]
                break

        logger.warning(
            "Using fallback (no-LLM) summarization. "
            "Set LLM_PROVIDER=openai and OPENAI_API_KEY for AI-generated summaries."
        )

        return """{
  "cluster_id": -1,
  "label": "[No LLM - Fallback Mode]",
  "core_emotions": ["[requires LLM provider]"],
  "typical_triggers": ["[requires LLM provider]"],
  "automatic_thoughts": ["[requires LLM provider]"],
  "behaviors": ["[requires LLM provider]"],
  "underlying_need": ["[requires LLM provider]"],
  "loop_summary": "Fallback mode: no LLM provider configured. Set LLM_PROVIDER=openai and OPENAI_API_KEY to enable AI summarization.",
  "representative_quotes": [],
  "related_clusters": []
}"""
