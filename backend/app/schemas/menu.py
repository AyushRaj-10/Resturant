"""Pydantic schemas for menu items."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MenuItemBase(BaseModel):
    """Base schema defining common menu item attributes."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique name of the menu item",
        examples=["Paneer Butter Masala"],
    )
    description: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Detailed description of the dish and ingredients",
        examples=["Cottage cheese simmered in velvety tomato makhani sauce."],
    )
    price: Decimal = Field(
        ...,
        gt=Decimal("0.00"),
        le=Decimal("100000.00"),
        decimal_places=2,
        description="Price in INR (> 0, maximum 2 decimal places, up to 100,000.00)",
        examples=[Decimal("310.00")],
    )
    available: bool = Field(
        default=True,
        description="Whether the dish is currently in stock and available to order",
        examples=[True],
    )

    @field_validator("name", mode="before")
    @classmethod
    def validate_and_strip_name(cls, value: str) -> str:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("Name cannot be empty or contain only whitespace.")
            return stripped
        return value

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: Optional[str]) -> Optional[str]:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped if stripped else None
        return value


class MenuItemCreate(MenuItemBase):
    """Input schema for creating a new menu item."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "name": "Chicken Tikka",
                "description": "Boneless chicken marinated in spiced yogurt and roasted in clay oven.",
                "price": "320.00",
                "available": True,
            }
        },
    )


class MenuItemOut(MenuItemBase):
    """Output schema representing a persisted menu item."""

    id: int = Field(..., description="Unique database ID of the menu item", examples=[1])
    created_at: datetime = Field(..., description="Timestamp when the item was added to the menu")

    model_config = ConfigDict(from_attributes=True)
