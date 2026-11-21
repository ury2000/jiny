"""Backward-compatible Google GenAI Interactions client for Jiny Companion."""

from __future__ import annotations

from typing import Any

from .config import DEFAULT_MODEL
from .providers import GeminiAPIKeyProvider


class JinyGeminiClient(GeminiAPIKeyProvider):
    """Thin stateful wrapper around google-genai Interactions API (v0.2 compatible)."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        client: Any = None,
    ) -> None:
        if client is None and not api_key:
            raise ValueError(
                "Missing GEMINI_API_KEY. Set the GEMINI_API_KEY environment variable "
                "or add 'api_key' in companion/config.json."
            )
        super().__init__(api_key=api_key, model=model, client=client)

    def ask(self, question: str, locale: str = "esES", context: str | None = None) -> str:
        """Send a question (and optional context) to Gemini and track conversation state."""
        return super().ask(question=question, locale=locale, context=context)