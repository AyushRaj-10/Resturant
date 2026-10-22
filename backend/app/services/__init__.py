"""Services package exposing business logic functions and domain exceptions."""

from app.services.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationRuleError,
)
from app.services.menu_service import (
    create_menu_item,
    get_menu_item,
    list_menu_items,
)
from app.services.order_rules import (
    ALLOWED_TRANSITIONS,
    Operation,
    assert_allowed,
    can_cancel,
    can_delete,
    can_transition,
    can_update_bill,
    can_update_quantity,
    explain_block,
    get_allowed_actions,
)
from app.services.order_service import (
    cancel_order,
    change_status,
    create_order,
    delete_order,
    get_allowed_actions_for_order,
    get_order,
    list_orders,
    update_bill,
    update_item_quantity,
)

__all__ = [
    # Exceptions
    "ServiceError",
    "NotFoundError",
    "ValidationRuleError",
    "ConflictError",
    # Order Rules
    "Operation",
    "ALLOWED_TRANSITIONS",
    "can_transition",
    "can_update_quantity",
    "can_update_bill",
    "can_cancel",
    "can_delete",
    "explain_block",
    "assert_allowed",
    "get_allowed_actions",
    # Menu Service
    "list_menu_items",
    "get_menu_item",
    "create_menu_item",
    # Order Service
    "create_order",
    "get_order",
    "list_orders",
    "update_item_quantity",
    "update_bill",
    "change_status",
    "cancel_order",
    "delete_order",
    "get_allowed_actions_for_order",
]
