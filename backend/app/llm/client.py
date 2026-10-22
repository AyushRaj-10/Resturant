"""Public client interface for LLM text and structured JSON generation.

Enforces strict isolation from database, services, and models.
Features graceful degradation with mandatory fallbacks, prompt sanitization,
delimiters, and non-leaking logging.
"""

from functools import lru_cache
import json
import logging
import re
import time
from typing import Optional, Tuple, Type, TypeVar
from pydantic import BaseModel
from app.config import Settings, get_settings
from app.llm.base import LLMProvider, LLMResult, sanitize_llm_text
from app.llm.prompts import BASE_SYSTEM_RULES
from app.llm.providers import AnthropicProvider, OpenAIProvider

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
MAX_USER_CONTENT_LENGTH = 4000


def _extract_json_string(raw_text: str) -> str:
    """Strip markdown code blocks or surrounding text to isolate JSON payload."""
    cleaned = raw_text.strip()
    fence_pattern = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fence_pattern:
        return fence_pattern.group(1).strip()
    return cleaned


class LLMClient:
    """Wrapper coordinating provider invocation, fallbacks, retries, and sanitization."""

    def __init__(self, settings: Settings):
        self.provider_name = settings.LLM_PROVIDER
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL
        self.timeout_seconds = settings.LLM_TIMEOUT_SECONDS
        self.max_tokens = settings.LLM_MAX_TOKENS
        self.temperature = settings.LLM_TEMPERATURE
        self.max_retries = max(0, settings.LLM_MAX_RETRIES)

        self._provider: Optional[LLMProvider] = None
        self._initialize_provider()

    def _initialize_provider(self) -> None:
        """Instantiate the configured provider if credentials and model are present."""
        if not self.is_available():
            self._provider = None
            return

        try:
            if self.provider_name == "openai":
                self._provider = OpenAIProvider(
                    api_key=self.api_key,
                    model=self.model,  # type: ignore[arg-type]
                    timeout_seconds=self.timeout_seconds,
                )
            elif self.provider_name == "anthropic":
                self._provider = AnthropicProvider(
                    api_key=self.api_key,
                    model=self.model,  # type: ignore[arg-type]
                    timeout_seconds=self.timeout_seconds,
                )
            else:
                self._provider = None
        except Exception as exc:
            logger.warning("Failed to initialize LLM provider '%s': %s", self.provider_name, exc)
            self._provider = None

    def is_available(self) -> bool:
        """Return True only if a supported provider is selected with key and model configured."""
        if self.provider_name in ("none", "", None):
            return False
        if not self.api_key or not self.api_key.strip():
            return False
        if not self.model or not self.model.strip():
            return False
        return self.provider_name in ("openai", "anthropic")

    def generate_text(
        self,
        task: str,
        system: str,
        user_content: str,
        fallback: str,
    ) -> LLMResult:
        """Generate text with safety boundary, fallbacks, and retry logic. Never raises."""
        start_time = time.perf_counter()
        truncated_user = user_content[:MAX_USER_CONTENT_LENGTH] if user_content else ""

        # Check availability
        if not self.is_available() or self._provider is None:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            logger.info(
                "LLM call finished: task=%s provider=%s model=%s latency_ms=%d source=fallback user_len=%d error=LLM not configured",
                task,
                self.provider_name,
                self.model,
                latency_ms,
                len(truncated_user),
            )
            return LLMResult(
                text=sanitize_llm_text(fallback),
                source="fallback",
                provider=self.provider_name,
                model=self.model if self.is_available() else None,
                latency_ms=latency_ms,
                error="LLM is not configured or disabled.",
            )

        # Wrap system prompt with standard safety boundary and user data delimiters
        full_system = f"{BASE_SYSTEM_RULES}\n\n{system}".strip()
        wrapped_user = f"<user_data>\n{truncated_user}\n</user_data>"

        last_error: Optional[str] = None
        attempts = 1 + self.max_retries

        for attempt in range(1, attempts + 1):
            try:
                raw_response = self._provider.generate(
                    system=full_system,
                    user=wrapped_user,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
                if not raw_response or not raw_response.strip():
                    raise ValueError("LLM returned empty completion.")

                sanitized = sanitize_llm_text(raw_response)
                latency_ms = int((time.perf_counter() - start_time) * 1000)

                logger.info(
                    "LLM call finished: task=%s provider=%s model=%s latency_ms=%d source=llm user_len=%d error=None",
                    task,
                    self.provider_name,
                    self.model,
                    latency_ms,
                    len(truncated_user),
                )
                return LLMResult(
                    text=sanitized,
                    source="llm",
                    provider=self.provider_name,
                    model=self.model,
                    latency_ms=latency_ms,
                    error=None,
                )
            except Exception as exc:
                err_text = f"{type(exc).__name__}: {str(exc)}"
                if self.api_key and self.api_key in err_text:
                    err_text = err_text.replace(self.api_key, "[REDACTED]")
                last_error = err_text
                logger.warning(
                    "LLM attempt %d/%d failed for task '%s': %s",
                    attempt,
                    attempts,
                    task,
                    last_error,
                )
                if attempt < attempts:
                    time.sleep(0.5)

        # All attempts failed: gracefully fall back
        latency_ms = int((time.perf_counter() - start_time) * 1000)
        logger.info(
            "LLM call finished: task=%s provider=%s model=%s latency_ms=%d source=fallback user_len=%d error=%s",
            task,
            self.provider_name,
            self.model,
            latency_ms,
            len(truncated_user),
            last_error,
        )
        return LLMResult(
            text=sanitize_llm_text(fallback),
            source="fallback",
            provider=self.provider_name,
            model=self.model,
            latency_ms=latency_ms,
            error=last_error,
        )

    def generate_json(
        self,
        task: str,
        system: str,
        user_content: str,
        schema: Type[T],
        fallback: Optional[T] = None,
    ) -> Tuple[Optional[T], LLMResult]:
        """Generate structured data strictly validated against a Pydantic schema."""
        json_system = (
            f"{system}\n\n"
            f"You MUST output valid JSON conforming strictly to this JSON Schema:\n"
            f"{json.dumps(schema.model_json_schema())}\n"
            f"Do NOT include markdown formatting, explanations, or any text other than the JSON object."
        )

        fallback_str = fallback.model_dump_json() if fallback is not None else "{}"
        result = self.generate_text(
            task=f"{task}_json",
            system=json_system,
            user_content=user_content,
            fallback=fallback_str,
        )

        if result.source == "fallback" and result.error:
            return fallback, result

        # Attempt to parse and validate
        json_candidate = _extract_json_string(result.text)
        try:
            validated = schema.model_validate_json(json_candidate)
            return validated, result
        except Exception as first_exc:
            logger.warning("JSON validation failed on attempt 1 for task '%s': %s", task, first_exc)

            # Retry once with explicit error feedback if LLM is active
            if result.source == "llm" and self.is_available() and self._provider:
                retry_user = (
                    f"{user_content}\n\n"
                    f"CRITICAL: Your previous response was invalid JSON. Validation error: {first_exc}.\n"
                    f"Return ONLY valid JSON matching the requested schema."
                )
                retry_result = self.generate_text(
                    task=f"{task}_json_retry",
                    system=json_system,
                    user_content=retry_user,
                    fallback=fallback_str,
                )
                if retry_result.source == "llm":
                    try:
                        retry_candidate = _extract_json_string(retry_result.text)
                        validated = schema.model_validate_json(retry_candidate)
                        return validated, retry_result
                    except Exception as retry_exc:
                        first_exc = retry_exc

            # Final validation failure
            return fallback, LLMResult(
                text=result.text,
                source="fallback",
                provider=self.provider_name,
                model=self.model,
                latency_ms=result.latency_ms,
                error=f"JSON validation error: {first_exc}",
            )


@lru_cache
def get_llm_client() -> LLMClient:
    """Return cached instance of LLMClient configured from application settings."""
    settings = get_settings()
    return LLMClient(settings)
