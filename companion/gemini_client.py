"""Official Google GenAI Interactions client for Jiny Companion."""

from __future__ import annotations

from typing import Any, Optional

from .config import DEFAULT_MODEL, sanitize_model_name
from .prompts import apply_rag_context, build_system_instruction


class JinyGeminiClient:
    """Thin stateful wrapper around google-genai Interactions API."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        client: Any = None,
    ) -> None:
        self.model = sanitize_model_name(model)
        self.last_interaction_id: Optional[str] = None
        if client is not None:
            self._client = client
        else:
            if not api_key:
                raise ValueError(
                    "Missing GEMINI_API_KEY. Set the GEMINI_API_KEY environment variable "
                    "or add 'api_key' in companion/config.json."
                )
            from google import genai

            self._client = genai.Client(api_key=api_key)

    def reset_session(self) -> None:
        """Clear stateful conversation tracking."""
        self.last_interaction_id = None

    def ask(self, question: str, locale: str = "esES", context: str | None = None) -> str:
        """Send a question to Gemini (optionally grounded with RAG context) and track conversation state."""
        clean_context = (context or "").strip()
        prompt_input = (
            apply_rag_context(question, clean_context, locale=locale)
            if clean_context
            else question
        )
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": prompt_input,
            "system_instruction": build_system_instruction(locale),
        }
        if self.last_interaction_id:
            kwargs["previous_interaction_id"] = self.last_interaction_id

        interaction = self._client.interactions.create(**kwargs)
        interaction_id = getattr(interaction, "id", None)
        if interaction_id:
            self.last_interaction_id = interaction_id

        text = getattr(interaction, "output_text", None) or ""
        return text.strip()
