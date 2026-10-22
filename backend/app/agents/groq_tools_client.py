"""Groq chat completions client with function-calling support.

Self-contained inside app/agents/ to preserve app/llm/ as generation-only.
"""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional
from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRaw:
    """Represents a raw function/tool call emitted by the model."""

    id: str
    name: str
    arguments: str  # Raw JSON string


@dataclass
class ChatCompletionResult:
    """Standardized response from the Groq tools chat endpoint."""

    content: Optional[str] = None
    tool_calls: List[ToolCallRaw] = field(default_factory=list)
    error: Optional[str] = None


class GroqToolsClient:
    """Client for Groq LLM tool-calling completions."""

    def __init__(self):
        self._client = None

    def is_available(self) -> bool:
        """Check whether Groq provider, API key, and model are configured."""
        settings = get_settings()
        if settings.LLM_PROVIDER != "groq":
            return False
        if not settings.LLM_API_KEY or not settings.LLM_API_KEY.strip():
            return False
        if not settings.LLM_MODEL or not settings.LLM_MODEL.strip():
            return False
        return True

    def _get_client(self):
        """Lazily initialize official Groq client."""
        if self._client is None:
            settings = get_settings()
            try:
                from groq import Groq
            except ImportError as exc:
                raise RuntimeError("groq package is not installed. Install with 'pip install groq'.") from exc

            timeout = float(getattr(settings, "LLM_TIMEOUT_SECONDS", 15))
            self._client = Groq(
                api_key=settings.LLM_API_KEY.strip(),
                timeout=timeout,
            )
        return self._client

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatCompletionResult:
        """Invoke Groq chat completion with function-calling tools. Never raises exceptions."""
        if not self.is_available():
            return ChatCompletionResult(error="Groq LLM is not configured or unavailable.")

        settings = get_settings()
        model_name = settings.LLM_MODEL.strip() if settings.LLM_MODEL else "llama-3.3-70b-versatile"
        temperature = float(getattr(settings, "LLM_TEMPERATURE", 0.2))

        logger.info(
            "Groq tool chat invocation: model=%s message_count=%d tool_count=%d",
            model_name,
            len(messages),
            len(tools) if tools else 0,
        )

        try:
            client = self._get_client()
            kwargs: Dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            completion = client.chat.completions.create(**kwargs)
            if not completion.choices:
                return ChatCompletionResult(error="Groq returned empty choices.")

            message = completion.choices[0].message
            content = message.content or None

            parsed_tool_calls: List[ToolCallRaw] = []
            if getattr(message, "tool_calls", None):
                for tc in message.tool_calls:
                    tc_id = getattr(tc, "id", "") or ""
                    fn = getattr(tc, "function", None)
                    fn_name = getattr(fn, "name", "") if fn else ""
                    fn_args = getattr(fn, "arguments", "{}") if fn else "{}"
                    parsed_tool_calls.append(
                        ToolCallRaw(id=tc_id, name=fn_name, arguments=fn_args)
                    )

            return ChatCompletionResult(
                content=content,
                tool_calls=parsed_tool_calls,
                error=None,
            )
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {str(exc)}"
            if settings.LLM_API_KEY and settings.LLM_API_KEY in err_msg:
                err_msg = err_msg.replace(settings.LLM_API_KEY, "[REDACTED]")
            logger.warning("Groq tool completion error: %s", err_msg)
            return ChatCompletionResult(error=err_msg)


_groq_tools_client: Optional[GroqToolsClient] = None


def get_groq_tools_client() -> GroqToolsClient:
    """Return singleton instance of GroqToolsClient."""
    global _groq_tools_client
    if _groq_tools_client is None:
        _groq_tools_client = GroqToolsClient()
    return _groq_tools_client
