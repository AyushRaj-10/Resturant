"""Pydantic schemas for order management and billing."""

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
from app.models.enums import OrderStatus


class OrderItemIn(BaseModel):
    """Input payload for a single item within an order."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "menu_item_id": 1,
                "quantity": 2,
            }
        },
    )

    menu_item_id: int = Field(
        ...,
        gt=0,
        description="ID of the menu item to order (> 0)",
        examples=[1],
    )
    quantity: int = Field(
        ...,
        ge=1,
        le=50,
        description="Quantity of the item to order (1 to 50)",
        examples=[2],
    )


class OrderItemOut(BaseModel):
    """Output representation of an item included in an order."""

    id: int = Field(..., description="Unique database ID of the line item")
    menu_item_id: int = Field(..., description="ID of the ordered menu item")
    menu_item_name: Optional[str] = Field(
        default=None,
        description="Name of the ordered menu item resolved from database",
        examples=["Paneer Tikka"],
    )
    quantity: int = Field(..., description="Quantity ordered")
    price_at_order_time: Decimal = Field(
        ...,
        description="Snapshot price per unit at the time the order was placed",
        examples=[Decimal("260.00")],
    )

    @computed_field
    @property
    def line_total(self) -> Decimal:
        """Total price for this line item (quantity * price_at_order_time)."""
        return Decimal(self.quantity) * self.price_at_order_time

    @model_validator(mode="before")
    @classmethod
    def resolve_item_attributes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            menu_item = getattr(data, "menu_item", None)
            menu_item_name = (
                getattr(menu_item, "name", None)
                if menu_item is not None
                else getattr(data, "menu_item_name", None)
            )
            return {
                "id": getattr(data, "id", None),
                "menu_item_id": getattr(data, "menu_item_id", None),
                "menu_item_name": menu_item_name,
                "quantity": getattr(data, "quantity", None),
                "price_at_order_time": getattr(data, "price_at_order_time", None),
            }
        return data

    model_config = ConfigDict(from_attributes=True)


class OrderCreate(BaseModel):
    """Input payload to create a new customer dining order."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "customer_name": "Rohan Gupta",
                "table_no": 5,
                "items": [
                    {"menu_item_id": 1, "quantity": 2},
                    {"menu_item_id": 8, "quantity": 3},
                ],
            }
        },
    )

    customer_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name of the customer placing the order (1-100 characters)",
        examples=["Rohan Gupta"],
    )
    table_no: int = Field(
        ...,
        ge=1,
        le=200,
        description="Dining table number (1 to 200)",
        examples=[5],
    )
    items: List[OrderItemIn] = Field(
        ...,
        min_length=1,
        max_length=30,
        description="List of menu items and quantities (1 to 30 items)",
    )

    @field_validator("customer_name", mode="before")
    @classmethod
    def validate_and_strip_customer_name(cls, value: str) -> str:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("Customer name cannot be empty or contain only whitespace.")
            return stripped
        return value

    @field_validator("items")
    @classmethod
    def validate_unique_menu_items(cls, items: List[OrderItemIn]) -> List[OrderItemIn]:
        seen = set()
        duplicates = set()
        for item in items:
            if item.menu_item_id in seen:
                duplicates.add(item.menu_item_id)
            seen.add(item.menu_item_id)
        if duplicates:
            raise ValueError(
                f"Duplicate menu_item_id(s) found: {sorted(duplicates)}. Please combine quantities into a single item entry."
            )
        return items


class OrderOut(BaseModel):
    """Detailed output schema representing a complete customer order."""

    id: int = Field(..., description="Unique database ID of the order")
    customer_name: str = Field(..., description="Customer name associated with order")
    table_no: int = Field(..., description="Dining table number")
    status: OrderStatus = Field(..., description="Current lifecycle status of the order")
    total_bill: Decimal = Field(..., description="Calculated total bill amount in INR")
    discount_percent: Optional[Decimal] = Field(
        default=None,
        description="Discount percentage applied to the order",
        examples=[Decimal("10.00")],
    )
    service_charge_percent: Optional[Decimal] = Field(
        default=None,
        description="Service charge percentage applied to the order",
        examples=[Decimal("5.00")],
    )
    items: List[OrderItemOut] = Field(
        default_factory=list,
        validation_alias=AliasChoices("items", "order_items"),
        description="List of ordered items with prices and quantities",
    )
    created_at: datetime = Field(..., description="Timestamp when order was placed")
    updated_at: datetime = Field(..., description="Timestamp when order was last updated")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class OrderSummary(BaseModel):
    """Lightweight representation of an order optimized for list views."""

    id: int = Field(..., description="Unique database ID of the order")
    customer_name: str = Field(..., description="Customer name")
    table_no: int = Field(..., description="Dining table number")
    status: OrderStatus = Field(..., description="Current order status")
    total_bill: Decimal = Field(..., description="Total bill in INR")
    item_count: int = Field(..., description="Total number of items in order")
    created_at: datetime = Field(..., description="Timestamp when order was placed")

    @model_validator(mode="before")
    @classmethod
    def resolve_summary_attributes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            order_items = getattr(data, "order_items", None)
            total_items = (
                sum(getattr(i, "quantity", 1) for i in order_items)
                if order_items is not None
                else 0
            )
            return {
                "id": getattr(data, "id", None),
                "customer_name": getattr(data, "customer_name", None),
                "table_no": getattr(data, "table_no", None),
                "status": getattr(data, "status", None),
                "total_bill": getattr(data, "total_bill", None),
                "item_count": getattr(data, "item_count", total_items),
                "created_at": getattr(data, "created_at", None),
            }
        return data

    model_config = ConfigDict(from_attributes=True)


class QuantityUpdate(BaseModel):
    """Input schema for updating the quantity of an item within an order."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "quantity": 3,
            }
        },
    )

    quantity: int = Field(
        ...,
        ge=1,
        le=50,
        description="New item quantity (1 to 50)",
        examples=[3],
    )


class BillUpdate(BaseModel):
    """Input schema for applying discounts or service charges to an order bill."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "discount_percent": "10.00",
                "service_charge_percent": "5.00",
            }
        },
    )

    discount_percent: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0.00"),
        le=Decimal("100.00"),
        decimal_places=2,
        description="Discount percentage to deduct from the subtotal (0.00% to 100.00%)",
        examples=[Decimal("10.00")],
    )
    service_charge_percent: Optional[Decimal] = Field(
        default=None,
        ge=Decimal("0.00"),
        le=Decimal("30.00"),
        decimal_places=2,
        description="Service charge percentage to add to the subtotal (0.00% to 30.00%)",
        examples=[Decimal("5.00")],
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "BillUpdate":
        if self.discount_percent is None and self.service_charge_percent is None:
            raise ValueError(
                "At least one of 'discount_percent' or 'service_charge_percent' must be provided."
            )
        return self


class StatusUpdate(BaseModel):
    """Input schema for transitioning an order's lifecycle status."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "status": "PREPARING",
            }
        },
    )

    status: OrderStatus = Field(
        ...,
        description="New lifecycle status for the order",
        examples=[OrderStatus.PREPARING],
    )


class AllowedActionsResponse(BaseModel):
    """Response payload detailing permitted operations for an order."""

    status: OrderStatus = Field(..., description="Current status of the order")
    allowed: List[str] = Field(..., description="List of permitted operational actions")

