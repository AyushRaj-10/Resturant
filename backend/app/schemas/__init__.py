"""Pydantic schemas package exporting all request, response, and filter models."""

from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConfirmRequest,
    AgentConfirmResponse,
    PendingActionOut,
)
from app.schemas.ai import (
    DraftOrderRequest,
    DraftOrderResponse,
    TextResponse,
    UpsellItem,
    UpsellResponse,
)
from app.schemas.audit import AgentAuditLogOut
from app.schemas.common import (
    ErrorResponse,
    MessageResponse,
    OrderFilter,
    PaginationParams,
)
from app.schemas.menu import MenuItemBase, MenuItemCreate, MenuItemOut
from app.schemas.order import (
    AllowedActionsResponse,
    BillUpdate,
    OrderCreate,
    OrderItemIn,
    OrderItemOut,
    OrderOut,
    OrderSummary,
    QuantityUpdate,
    StatusUpdate,
)

__all__ = [
    # Common
    "MessageResponse",
    "ErrorResponse",
    "PaginationParams",
    "OrderFilter",
    # Menu
    "MenuItemBase",
    "MenuItemCreate",
    "MenuItemOut",
    # Order
    "OrderItemIn",
    "OrderItemOut",
    "OrderCreate",
    "OrderOut",
    "OrderSummary",
    "QuantityUpdate",
    "BillUpdate",
    "StatusUpdate",
    "AllowedActionsResponse",
    # Audit
    "AgentAuditLogOut",
    # AI Features
    "TextResponse",
    "UpsellItem",
    "UpsellResponse",
    "DraftOrderRequest",
    "DraftOrderResponse",
    # Agent
    "AgentChatRequest",
    "AgentChatResponse",
    "AgentConfirmRequest",
    "AgentConfirmResponse",
    "PendingActionOut",
]
