"""Schemas for Generative AI feature requests and responses."""

from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.order import OrderCreate


class TextResponse(BaseModel):
    """Generic text response with source attribution."""

    message: str = Field(..., description="Generated or template-based text message")
    source: Literal["llm", "fallback"] = Field(..., description="Whether content came from LLM or template fallback")


class UpsellItem(BaseModel):
    """Individual menu suggestion paired with an order."""

    menu_item_id: int = Field(..., description="ID of the recommended menu item")
    menu_item_name: str = Field(..., description="Name of the recommended item")
    price: Decimal = Field(..., description="Current price in INR")
    reason: str = Field(..., description="Appetizing reason for recommendation")


class UpsellResponse(BaseModel):
    """List of upsell item recommendations."""

    suggestions: List[UpsellItem] = Field(default_factory=list, description="Curated menu item recommendations")
    source: Literal["llm", "fallback"] = Field(..., description="Whether suggestions were synthesized by LLM or rule fallback")


class DraftOrderRequest(BaseModel):
    """Input payload providing natural language to draft an order."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "text": "Table 4, Rahul wants 2 butter naan and one paneer tikka",
            }
        },
    )

    text: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language order description (1-500 characters)",
        examples=["Table 4, Rahul wants 2 butter naan and one paneer tikka"],
    )


class DraftOrderResponse(BaseModel):
    """Proposed order draft parsed from natural language. Never saves automatically."""

    draft: Optional[OrderCreate] = Field(
        default=None,
        description="Structured order create payload if valid items were detected, else None",
    )
    unmatched: List[str] = Field(
        default_factory=list,
        description="Items or words from the text that could not be matched to available menu items",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Validation notices regarding customer name, table number, or quantities",
    )
    estimated_total: Decimal = Field(
        default=Decimal("0.00"),
        description="Estimated total cost in INR based on matched items",
    )
    source: Literal["llm", "fallback"] = Field(
        ...,
        description="Whether draft parsing was performed by LLM or fallback heuristics",
    )
    requires_confirmation: bool = Field(
        default=True,
        description="Always true. Drafts must be explicitly reviewed and confirmed before creation.",
    )
