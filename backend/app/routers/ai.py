"""API Router for AI service status and connectivity verification."""

from typing import Literal, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.llm import (
    LLMClient,
    LLMResult,
    RESTAURANT_ASSISTANT_PERSONA,
    get_llm_client,
)

router = APIRouter(prefix="/ai", tags=["AI"])


class AIStatusResponse(BaseModel):
    """Health and configuration status of the AI layer."""

    available: bool = Field(..., description="Whether a valid LLM provider and model are active")
    provider: str = Field(..., description="Configured LLM provider name ('none', 'openai', 'anthropic')")
    model: Optional[str] = Field(default=None, description="Active model identifier if available")
    mode: Literal["llm", "fallback"] = Field(..., description="Operational mode currently in effect")


@router.get(
    "/status",
    response_model=AIStatusResponse,
    summary="Get AI service status",
    description="Inspect whether the Generative AI layer is operational or running in fallback mode.",
)
def get_ai_status(client: LLMClient = Depends(get_llm_client)) -> AIStatusResponse:
    available = client.is_available()
    return AIStatusResponse(
        available=available,
        provider=client.provider_name,
        model=client.model if available else None,
        mode="llm" if available else "fallback",
    )


@router.post(
    "/ping",
    response_model=LLMResult,
    summary="Verify LLM generation and fallback pipeline",
    description="Trigger a test prompt to verify the LLM connection or fallback behavior.",
)
def ping_ai(client: LLMClient = Depends(get_llm_client)) -> LLMResult:
    fallback_greeting = "Welcome to our restaurant! We are delighted to host you today."
    return client.generate_text(
        task="ping",
        system=RESTAURANT_ASSISTANT_PERSONA,
        user_content="Reply with one short friendly sentence welcoming a restaurant guest.",
        fallback=fallback_greeting,
    )
