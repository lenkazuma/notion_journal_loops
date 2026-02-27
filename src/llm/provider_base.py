"""
Abstract base class for LLM providers.
All providers must implement embed() and chat().
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ProviderBase(ABC):
    """
    Abstract LLM provider interface.

    Implementations:
      - ProviderOpenAI   (provider_openai.py)
      - ProviderAnthropic (provider_anthropic.py)
      - ProviderFallback  (provider_fallback.py) — no API key required
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    def supports_embedding(self) -> bool:
        """Return True if this provider can generate embeddings."""
        return False

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Parameters
        ----------
        texts : list of strings to embed

        Returns
        -------
        List of embedding vectors (list of floats)

        Raises
        ------
        NotImplementedError if provider doesn't support embeddings
        """
        ...

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs: Any) -> str:
        """
        Send a chat completion request.

        Parameters
        ----------
        messages : list of {"role": "user"|"assistant"|"system", "content": str}
        **kwargs : additional model parameters (temperature, max_tokens, etc.)

        Returns
        -------
        The assistant's response text
        """
        ...

    def chat_json(self, messages: List[Dict[str, str]], **kwargs: Any) -> Dict:
        """
        Chat and parse the response as JSON.
        Strips markdown code fences if present.
        """
        import json
        import re

        response = self.chat(messages, **kwargs)

        # Strip markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", response.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to extract JSON object/array from response
            match = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', cleaned)
            if match:
                return json.loads(match.group())
            raise ValueError(f"Could not parse JSON from response:\n{response[:500]}")
