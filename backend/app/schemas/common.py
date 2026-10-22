"""Common schemas shared across routes and future services."""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import OrderStatus


class MessageResponse(BaseModel):
    """Generic success message response."""

    message: str = Field(
        ...,
        description="Informational status message",
        examples=["Operation completed successfully"],
    )


class ErrorResponse(BaseModel):
    """Structured error response schema."""

    detail: str = Field(
        ...,
        description="Human-readable explanation of the error",
        examples=["Resource not found or validation failed"],
    )
    code: Optional[str] = Field(
        default=None,
        description="Machine-readable error classification code",
        examples=["ORDER_NOT_FOUND", "INVALID_TRANSITION"],
    )


class PaginationParams(BaseModel):
    """Query parameters for paginated list endpoints."""

    model_config = ConfigDict(extra="forbid")

    skip: int = Field(
        default=0,
        ge=0,
        description="Number of records to skip for pagination",
        examples=[0],
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of records to return (1-100)",
        examples=[20],
    )


class OrderFilter(BaseModel):
    """Filtering options for querying orders."""

    model_config = ConfigDict(extra="forbid")

    status: Optional[OrderStatus] = Field(
        default=None,
        description="Filter orders by current status",
        examples=[OrderStatus.PLACED],
    )
    table_no: Optional[int] = Field(
        default=None,
        ge=1,
        le=200,
        description="Filter orders by dining table number (1-200)",
        examples=[5],
    )
