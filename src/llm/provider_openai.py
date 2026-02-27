"""
OpenAI provider: supports both embeddings and chat completions.
Uses openai>=1.0 SDK.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from src.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, OPENAI_EMBED_MODEL
from src.llm.provider_base import ProviderBase
from src.utils.logger import get_logger
from src.utils.retry import api_retry

logger = get_logger("llm.openai")

_EMBED_BATCH_SIZE = 100  # OpenAI allows up to 2048 inputs, but batch smaller for safety


class ProviderOpenAI(ProviderBase):
    """OpenAI provider using text-embedding-3-small + gpt-4o-mini by default."""

    def __init__(
        self,
        api_key: str | None = None,
        embed_model: str | None = None,
        chat_model: str | None = None,
    ) -> None:
        self._api_key = api_key or OPENAI_API_KEY
        self._embed_model = embed_model or OPENAI_EMBED_MODEL
        self._chat_model = chat_model or OPENAI_CHAT_MODEL
        self._client = None

    @property
    def name(self) -> str:
        return "openai"

    @property
    def supports_embedding(self) -> bool:
        return True

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    @api_retry(max_attempts=6, min_wait=1.0, max_wait=60.0)
    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        client = self._get_client()
        response = client.embeddings.create(
            model=self._embed_model,
            input=texts,
        )
        # Sort by index to ensure order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed texts in batches."""
        if not texts:
            return []
        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[i: i + _EMBED_BATCH_SIZE]
            logger.debug(f"Embedding batch {i // _EMBED_BATCH_SIZE + 1} ({len(batch)} texts)")
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)
            if i + _EMBED_BATCH_SIZE < len(texts):
                time.sleep(0.5)
        return all_embeddings

    @api_retry(max_attempts=5, min_wait=1.0, max_wait=30.0)
    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """Send chat completion request."""
        client = self._get_client()
        params = {
            "model": self._chat_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.3),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        response = client.chat.completions.create(**params)
        return response.choices[0].message.content or ""
