"""Vendor implementations for OpenAI and Anthropic LLM providers.

Imports SDKs lazily so that the application can start without errors
even when vendor packages are absent.
"""

from app.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI implementation using chat completions API."""

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
            import openai
        except ImportError as exc:
            raise RuntimeError("The 'openai' package is required for OpenAIProvider.") from exc

        client = openai.OpenAI(
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


class AnthropicProvider(LLMProvider):
    """Anthropic implementation using messages API."""

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
            import anthropic
        except ImportError as exc:
            raise RuntimeError("The 'anthropic' package is required for AnthropicProvider.") from exc

        client = anthropic.Anthropic(
            api_key=self.api_key,
            timeout=float(self.timeout_seconds),
        )

        response = client.messages.create(
            model=self.model,
            system=system,
            messages=[
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if not response.content:
            return ""

        # Extract text from text blocks
        parts = [block.text for block in response.content if hasattr(block, "text")]
        return "".join(parts)
