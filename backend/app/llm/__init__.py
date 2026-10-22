"""LLM package providing safe generative capabilities with guaranteed fallbacks."""

from app.llm.base import LLMProvider, LLMResult, sanitize_llm_text
from app.llm.client import LLMClient, get_llm_client
from app.llm.prompts import BASE_SYSTEM_RULES, RESTAURANT_ASSISTANT_PERSONA

__all__ = [
    "LLMClient",
    "LLMResult",
    "LLMProvider",
    "get_llm_client",
    "sanitize_llm_text",
    "BASE_SYSTEM_RULES",
    "RESTAURANT_ASSISTANT_PERSONA",
]
