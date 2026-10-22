"""Strict Pydantic argument schemas for all agent tools.

Every schema enforces extra="forbid" and provides rich field descriptions for LLM function calling.
"""

from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models.enums import OrderStatus
from app.schemas.order import OrderItemIn


class GetMenuArgs(BaseModel):
    """Arguments for retrieving the restaurant menu."""

    model_config = ConfigDict(extra="forbid")

    only_available: bool = Field(
        default=True,
        description="When true, returns only currently available menu items. When false, returns all menu items.",
    )


class ListOrdersArgs(BaseModel):
    """Arguments for listing restaurant orders."""

    model_config = ConfigDict(extra="forbid")

    status: Optional[OrderStatus] = Field(
        default=None,
        description="Filter orders by lifecycle status (PLACED, PREPARING, SERVED, CANCELLED, PAID).",
    )
    table_no: Optional[int] = Field(
        default=None,
        ge=1,
        le=200,
        description="Filter orders by dining table number (1 to 200).",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum number of orders to return (1 to 20, default 10).",
    )


class GetOrderArgs(BaseModel):
    """Arguments for retrieving a single order by ID."""

    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(
        ...,
        gt=0,
        description="Unique database ID of the order to look up.",
    )


class CreateOrderArgs(BaseModel):
    """Arguments for placing a new customer dining order."""

    model_config = ConfigDict(extra="forbid")

    customer_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name of the customer placing the order (1 to 100 characters).",
    )
    table_no: int = Field(
        ...,
        ge=1,
        le=200,
        description="Dining table number where customer is seated (1 to 200).",
    )
    items: List[OrderItemIn] = Field(
        ...,
        min_length=1,
        max_length=30,
        description="List of menu item IDs and quantities to order (at least 1 item required).",
    )

    @field_validator("customer_name")
    @classmethod
    def validate_name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Customer name cannot be empty or whitespace only.")
        return stripped


class UpdateQuantityArgs(BaseModel):
    """Arguments for changing the quantity of a line item in an active PLACED order."""

    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(
        ...,
        gt=0,
        description="Unique ID of the order containing the line item.",
    )
    item_id: int = Field(
        ...,
        gt=0,
        description="Unique ID of the order line item to update.",
    )
    quantity: int = Field(
        ...,
        ge=1,
        le=50,
        description="New quantity for this line item (1 to 50).",
    )


class UpdateBillArgs(BaseModel):
    """Arguments for applying discount or service charge to an order."""

    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(
        ...,
        gt=0,
        description="Unique ID of the order to update billing for.",
    )
    discount_percent: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
        description="Discount percentage to deduct from the items subtotal (0.00% to 100.00%).",
    )
    service_charge_percent: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0.00"),
        le=Decimal("30.00"),
        description="Service charge percentage to add to the items subtotal (0.00% to 30.00%).",
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "UpdateBillArgs":
        if self.discount_percent is None and self.service_charge_percent is None:
            raise ValueError(
                "At least one of 'discount_percent' or 'service_charge_percent' must be provided."
            )
        return self


class GetAllowedActionsArgs(BaseModel):
    """Arguments for querying allowed lifecycle actions for an order."""

    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(
        ...,
        gt=0,
        description="Unique ID of the order to inspect.",
    )


class CancelOrderArgs(BaseModel):
    """Arguments for cancelling an active PLACED order. Affects exactly one order."""

    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(
        ...,
        gt=0,
        description="Unique ID of the PLACED order to cancel.",
    )


class DeleteOrderArgs(BaseModel):
    """Arguments for permanently deleting a cancelled or paid order. Affects exactly one order."""

    model_config = ConfigDict(extra="forbid")

    order_id: int = Field(
        ...,
        gt=0,
        description="Unique ID of the terminal (CANCELLED or PAID) order to delete.",
    )
