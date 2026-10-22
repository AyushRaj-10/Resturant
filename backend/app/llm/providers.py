"""Groq provider adapter for the LLM abstraction layer.

Imports the official groq SDK lazily so the application boots
even when the package is missing.
"""

from app.llm.base import LLMProvider


class GroqProvider(LLMProvider):
    """Groq API implementation using chat completions."""

    def __init__(self, api_key: str, model: str, timeout_seconds: int = 15):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError("The 'groq' package is required for GroqProvider.") from exc

        client = Groq(
            api_key=self.api_key,
            timeout=float(self.timeout_seconds),
        )

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message or not choice.message.content:
            return ""
        return choice.message.content
