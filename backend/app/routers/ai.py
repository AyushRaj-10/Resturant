"""API Router for AI service status and Generative AI features."""

from typing import Literal, Optional
from fastapi import APIRouter, Depends, Path, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.llm import (
    LLMClient,
    LLMResult,
    RESTAURANT_ASSISTANT_PERSONA,
    get_llm_client,
)
from app.routers.rate_limiter import check_ai_rate_limit
from app.schemas.ai import (
    DraftOrderRequest,
    DraftOrderResponse,
    TextResponse,
    UpsellResponse,
)
from app.services import ai_features

router = APIRouter(prefix="/ai", tags=["AI"])


class AIStatusResponse(BaseModel):
    """Health and configuration status of the AI layer."""

    available: bool = Field(..., description="Whether a valid LLM provider and model are active")
    provider: str = Field(..., description="Configured LLM provider name ('none', 'groq')")
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


# =========================================================================
# Feature Endpoints (Rate Limited, Read-Only with DB)
# =========================================================================

@router.get(
    "/orders/{order_id}/confirmation",
    response_model=TextResponse,
    summary="Generate order confirmation message",
    description="Generate a warm, friendly customer confirmation message with verified total.",
    dependencies=[Depends(check_ai_rate_limit)],
)
def get_order_confirmation(
    order_id: int = Path(..., gt=0, description="Order ID"),
    db: Session = Depends(get_db),
) -> TextResponse:
    return ai_features.generate_confirmation(db=db, order_id=order_id)


@router.get(
    "/orders/{order_id}/summary",
    response_model=TextResponse,
    summary="Generate order summary and next steps",
    description="Summarize current order details, status, and permitted next lifecycle actions.",
    dependencies=[Depends(check_ai_rate_limit)],
)
def get_order_summary(
    order_id: int = Path(..., gt=0, description="Order ID"),
    db: Session = Depends(get_db),
) -> TextResponse:
    return ai_features.generate_summary(db=db, order_id=order_id)


@router.get(
    "/orders/{order_id}/bill-explanation",
    response_model=TextResponse,
    summary="Generate plain-language bill explanation",
    description="Explain subtotal, discounts, service charges, and total amount in simple terms.",
    dependencies=[Depends(check_ai_rate_limit)],
)
def get_bill_explanation(
    order_id: int = Path(..., gt=0, description="Order ID"),
    db: Session = Depends(get_db),
) -> TextResponse:
    return ai_features.explain_bill(db=db, order_id=order_id)


@router.get(
    "/orders/{order_id}/suggestions",
    response_model=UpsellResponse,
    summary="Generate upsell recommendations",
    description="Recommend up to 3 complementary available items not already in the order.",
    dependencies=[Depends(check_ai_rate_limit)],
)
def get_upsell_suggestions(
    order_id: int = Path(..., gt=0, description="Order ID"),
    db: Session = Depends(get_db),
) -> UpsellResponse:
    return ai_features.suggest_additions(db=db, order_id=order_id)


@router.get(
    "/menu/{item_id}/description",
    response_model=TextResponse,
    summary="Generate menu item description",
    description="Generate an appetizing description (up to 30 words) for a dish. Does not save to DB.",
    dependencies=[Depends(check_ai_rate_limit)],
)
def get_menu_item_description(
    item_id: int = Path(..., gt=0, description="Menu Item ID"),
    db: Session = Depends(get_db),
) -> TextResponse:
    return ai_features.describe_menu_item(db=db, item_id=item_id)


@router.post(
    "/draft-order",
    response_model=DraftOrderResponse,
    summary="Parse natural language into an order draft",
    description="Extract customer name, table number, and items into an uncommitted draft proposal. Never creates an order.",
    dependencies=[Depends(check_ai_rate_limit)],
)
def post_draft_order(
    payload: DraftOrderRequest,
    db: Session = Depends(get_db),
) -> DraftOrderResponse:
    return ai_features.draft_order_from_text(db=db, text=payload.text)
