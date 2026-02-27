"""
Anthropic Claude provider: supports chat completions only.
Embeddings fall back to TF-IDF (via provider_fallback).
"""
from __future__ import annotations

from typing import Any, Dict, List

from src.config import ANTHROPIC_API_KEY, ANTHROPIC_CHAT_MODEL
from src.llm.provider_base import ProviderBase
from src.utils.logger import get_logger
from src.utils.retry import api_retry

logger = get_logger("llm.anthropic")


class ProviderAnthropic(ProviderBase):
    """Anthropic Claude provider. No native embedding support."""

    def __init__(
        self,
        api_key: str | None = None,
        chat_model: str | None = None,
    ) -> None:
        self._api_key = api_key or ANTHROPIC_API_KEY
        self._chat_model = chat_model or ANTHROPIC_CHAT_MODEL
        self._client = None

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def supports_embedding(self) -> bool:
        return False

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Anthropic does not provide an embedding API.
        Raises NotImplementedError — the embedder.py will fall back to TF-IDF.
        """
        raise NotImplementedError(
            "Anthropic does not support embeddings. "
            "The pipeline will use TF-IDF vectors instead."
        )

    @api_retry(max_attempts=5, min_wait=1.0, max_wait=30.0)
    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """Send chat completion via Anthropic Messages API."""
        client = self._get_client()

        # Separate system message from conversation
        system_content = ""
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            else:
                conversation.append({"role": msg["role"], "content": msg["content"]})

        params: Dict[str, Any] = {
            "model": self._chat_model,
            "messages": conversation,
            "max_tokens": kwargs.get("max_tokens", 2048),
        }
        if system_content:
            params["system"] = system_content

        response = client.messages.create(**params)
        return response.content[0].text if response.content else ""
