"""API Router for Order management and billing endpoints."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.enums import OrderStatus
from app.schemas.common import MessageResponse, OrderFilter, PaginationParams
from app.schemas.order import (
    BillUpdate,
    OrderCreate,
    OrderOut,
    OrderSummary,
    QuantityUpdate,
)
from app.services import order_service

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new customer order",
    description="Create an order with line items, validating item existence and availability.",
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


@router.patch(
    "/{order_id}/items/{item_id}",
    response_model=OrderOut,
    summary="Update item quantity in order",
    description="Change the quantity of an item belonging to this order and recalculate the total bill.",
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
    description="Recalculate base item total and apply discount and/or service charge percentages.",
)
def update_bill(
    payload: BillUpdate,
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    db: Session = Depends(get_db),
) -> OrderOut:
    return order_service.update_bill(db=db, order_id=order_id, data=payload)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderOut,
    summary="Cancel an order",
    description="Set the order status to CANCELLED.",
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
    description="Permanently delete the order and cascade delete all its line items.",
)
def delete_order(
    order_id: int = Path(..., gt=0, description="Positive integer order ID"),
    db: Session = Depends(get_db),
) -> MessageResponse:
    order_service.delete_order(db=db, order_id=order_id)
    return MessageResponse(message=f"Order {order_id} deleted successfully.")
