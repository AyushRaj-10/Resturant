"""Pure business rules for Order lifecycle transitions and operational permissions.

No database dependencies or side-effects. Reusable across services, routers,
and future AI agent guardrails.
"""

import enum
from typing import Dict, List, Optional, Set
from app.models.enums import OrderStatus
from app.services.exceptions import ConflictError


class Operation(str, enum.Enum):
    """Business operations that can be performed on orders."""

    UPDATE_QUANTITY = "update_quantity"
    UPDATE_BILL = "update_bill"
    CANCEL = "cancel"
    DELETE = "delete"
    CHANGE_STATUS = "change_status"


# Permitted lifecycle state transitions
ALLOWED_TRANSITIONS: Dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.PLACED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
    OrderStatus.PREPARING: {OrderStatus.SERVED},
    OrderStatus.SERVED: {OrderStatus.PAID},
    OrderStatus.PAID: set(),       # Terminal state
    OrderStatus.CANCELLED: set(),  # Terminal state
}


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    """Check if transitioning from current to target status is valid."""
    return target in ALLOWED_TRANSITIONS.get(current, set())


def can_update_quantity(status: OrderStatus) -> bool:
    """Item quantities can only be modified before kitchen begins preparation."""
    return status == OrderStatus.PLACED


def can_update_bill(status: OrderStatus) -> bool:
    """Bill discounts and service charges can be adjusted while order is active."""
    return status in {OrderStatus.PLACED, OrderStatus.PREPARING, OrderStatus.SERVED}


def can_cancel(status: OrderStatus) -> bool:
    """Orders can only be cancelled while in PLACED status before preparation starts."""
    return status == OrderStatus.PLACED


def can_delete(status: OrderStatus) -> bool:
    """Orders can only be deleted once cancelled or settled/paid."""
    return status in {OrderStatus.CANCELLED, OrderStatus.PAID}


def explain_block(
    operation: str | Operation,
    status: OrderStatus,
    target_status: Optional[OrderStatus] = None,
    order_id: Optional[int] = None,
) -> str:
    """Produce specific, human-readable explanations of why an operation is blocked."""
    op_str = operation.value if isinstance(operation, Operation) else str(operation)
    order_ref = f"Order {order_id}" if order_id is not None else "Order"

    if op_str == Operation.CANCEL:
        if status == OrderStatus.CANCELLED:
            return f"{order_ref} is already CANCELLED."
        return (
            f"{order_ref} cannot be cancelled because it is already {status.value}. "
            f"Only PLACED orders can be cancelled."
        )

    if op_str == Operation.UPDATE_QUANTITY:
        return (
            f"{order_ref} item quantity cannot be updated because its status is {status.value}. "
            f"Item quantities can only be modified when an order is PLACED."
        )

    if op_str == Operation.UPDATE_BILL:
        return (
            f"{order_ref} bill adjustments cannot be applied because its status is {status.value}. "
            f"Bill discounts and service charges are only allowed on PLACED, PREPARING, or SERVED orders."
        )

    if op_str == Operation.DELETE:
        return (
            f"{order_ref} cannot be deleted because its status is {status.value}. "
            f"Only CANCELLED or PAID orders can be deleted."
        )

    if op_str == Operation.CHANGE_STATUS:
        valid_targets = [s.value for s in sorted(ALLOWED_TRANSITIONS.get(status, set()), key=lambda x: x.value)]
        target_str = target_status.value if target_status else "unknown"
        if not valid_targets:
            return (
                f"{order_ref} is in terminal status {status.value} and cannot be transitioned to {target_str}."
            )
        return (
            f"{order_ref} cannot transition from {status.value} to {target_str}. "
            f"Allowed transitions from {status.value} are: {', '.join(valid_targets)}."
        )

    return f"Operation '{op_str}' is not permitted for {order_ref} in status {status.value}."


def assert_allowed(
    operation: str | Operation,
    status: OrderStatus,
    target_status: Optional[OrderStatus] = None,
    order_id: Optional[int] = None,
) -> None:
    """Validate operation against order status, raising ConflictError with clear message if disallowed."""
    op_str = operation.value if isinstance(operation, Operation) else str(operation)
    allowed = False

    if op_str == Operation.UPDATE_QUANTITY:
        allowed = can_update_quantity(status)
    elif op_str == Operation.UPDATE_BILL:
        allowed = can_update_bill(status)
    elif op_str == Operation.CANCEL:
        allowed = can_cancel(status)
    elif op_str == Operation.DELETE:
        allowed = can_delete(status)
    elif op_str == Operation.CHANGE_STATUS:
        if target_status is not None:
            allowed = can_transition(status, target_status)
    else:
        allowed = False

    if not allowed:
        reason = explain_block(
            operation=op_str,
            status=status,
            target_status=target_status,
            order_id=order_id,
        )
        raise ConflictError(message=reason, code="OPERATION_NOT_ALLOWED")


def get_allowed_actions(status: OrderStatus) -> List[str]:
    """Compile list of permitted action identifiers for the given order status."""
    actions: List[str] = []

    if can_update_quantity(status):
        actions.append(Operation.UPDATE_QUANTITY.value)

    if can_update_bill(status):
        actions.append(Operation.UPDATE_BILL.value)

    if can_cancel(status):
        actions.append(Operation.CANCEL.value)

    if can_delete(status):
        actions.append(Operation.DELETE.value)

    for target in sorted(ALLOWED_TRANSITIONS.get(status, set()), key=lambda x: x.value):
        actions.append(f"change_status:{target.value}")

    return actions
