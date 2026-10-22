"""API Router for Order management, lifecycle state transitions, and billing."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import OrderStatus
from app.schemas.common import MessageResponse, OrderFilter, PaginationParams
from app.schemas.order import (
    AllowedActionsResponse,
    BillUpdate,
    OrderCreate,
    OrderOut,
    OrderSummary,
    QuantityUpdate,
    StatusUpdate,
)
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer order",
    description="Create an order with line items. Validates item existence and availability. Initial status is PLACED.",
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.create_order(db=db, data=payload)


@router.get(
    "",
    response_model=List[OrderSummary],
    summary="List orders",
    description="Retrieve paginated list of orders, optionally filtered by status and table number.",
)
def list_orders(
    status_filter: Optional[OrderStatus] = Query(
        default=None,
        alias="status",
        description="Filter orders by status",
    ),
    table_no: Optional[int] = Query(
        default=None,
        ge=1,
        le=200,
        description="Filter orders by table number (1-200)",
    ),
    skip: int = Query(default=0, ge=0, description="Records to skip"),
    limit: int = Query(default=20, ge=1, le=100, description="Max records to return"),
    db: Session = Depends(get_db),
) -> List[OrderSummary]:
    filters = OrderFilter(status=status_filter, table_no=table_no)
    pagination = PaginationParams(skip=skip, limit=limit)
    return order_service.list_orders(db=db, filters=filters, pagination=pagination)


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Retrieve order by ID",
    description="Fetch complete order details including all line items and current total bill.",
)
def get_order(
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.get_order(db=db, order_id=order_id)


@router.get(
    "/{order_id}/allowed-actions",
    response_model=AllowedActionsResponse,
    summary="Get permitted actions for order",
    description="Inspect current order status and return list of valid operational actions and state transitions.",
)
def get_order_allowed_actions(
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    db: Session = Depends(get_db),
) -> AllowedActionsResponse:
    actions_info = order_service.get_allowed_actions_for_order(db=db, order_id=order_id)
    return AllowedActionsResponse(
        status=actions_info["status"],
        allowed=actions_info["allowed"],
    )


@router.patch(
    "/{order_id}/items/{item_id}",
    response_model=OrderOut,
    summary="Update item quantity in order",
    description="Change item quantity and recalculate total bill. Allowed ONLY when order status is PLACED.",
)
def update_item_quantity(
    payload: QuantityUpdate,
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    item_id: int = Path(..., gt=0, description="Positive integer order item ID"),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.update_item_quantity(
        db=db,
        order_id=order_id,
        item_id=item_id,
        new_quantity=payload.quantity,
    )


@router.patch(
    "/{order_id}/bill",
    response_model=OrderOut,
    summary="Apply discount or service charge",
    description="Idempotently apply discount and/or service charge percentages. Allowed when status is PLACED, PREPARING, or SERVED.",
)
def update_bill(
    payload: BillUpdate,
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.update_bill(db=db, order_id=order_id, data=payload)


@router.post(
    "/{order_id}/status",
    response_model=OrderOut,
    summary="Transition order status",
    description=(
        "Transition order to a new lifecycle status. Valid flows: "
        "PLACED -> PREPARING or CANCELLED; "
        "PREPARING -> SERVED; "
        "SERVED -> PAID. "
        "PAID and CANCELLED are terminal states."
    ),
)
def change_order_status(
    payload: StatusUpdate,
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.change_status(
        db=db,
        order_id=order_id,
        target_status=payload.status,
    )


@router.post(
    "/{order_id}/cancel",
    response_model=OrderOut,
    summary="Cancel an order",
    description="Set order status to CANCELLED. Allowed ONLY when order status is PLACED.",
)
def cancel_order(
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.cancel_order(db=db, order_id=order_id)


@router.delete(
    "/{order_id}",
    response_model=MessageResponse,
    summary="Delete an order",
    description="Permanently delete an order and cascade delete line items. Allowed ONLY when status is CANCELLED or PAID.",
)
def delete_order(
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    db: Session = Depends(get_db),
) -> MessageResponse:
    order_service.delete_order(db=db, order_id=order_id)
    return MessageResponse(message=f"Order {order_id} deleted successfully.")
