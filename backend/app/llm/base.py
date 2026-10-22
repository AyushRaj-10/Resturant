"""Base types, data structures, and interfaces for the LLM abstraction layer."""

from abc import ABC, abstractmethod
import re
from typing import Literal, Optional
from pydantic import BaseModel, Field


class LLMResult(BaseModel):
    """Normalized result returned from an LLM invocation or fallback."""

    text: str = Field(..., description="Generated text response or fallback text")
    source: Literal["llm", "fallback"] = Field(..., description="Whether output came from LLM or fallback")
    provider: str = Field(..., description="Provider identifier (e.g. 'anthropic', 'openai', 'none')")
    model: Optional[str] = Field(default=None, description="Model identifier if LLM was invoked")
    latency_ms: int = Field(default=0, ge=0, description="Round-trip latency in milliseconds")
    error: Optional[str] = Field(default=None, description="Error explanation if fallback was triggered")


class LLMProvider(ABC):
    """Abstract base class for vendor-specific LLM implementations."""

    @abstractmethod
    def generate(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Execute a text completion with system and user messages."""
        pass


def sanitize_llm_text(text: str, max_len: int = 1500) -> str:
    """Strip control characters, trim whitespace, and enforce maximum length."""
    if not text:
        return ""

    # Remove non-printable control characters except standard whitespace (\t, \n, \r)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    trimmed = cleaned.strip()

    if len(trimmed) > max_len:
        return trimmed[:max_len].rstrip()
    return trimmed
