"""Service layer for Order business operations and billing calculations."""

from decimal import Decimal, ROUND_HALF_UP
from typing import List
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from app.models.enums import OrderStatus
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem
from app.schemas.common import OrderFilter, PaginationParams
from app.schemas.order import BillUpdate, OrderCreate
from app.services.exceptions import NotFoundError, ValidationRuleError


def _recalculate_total(order: Order) -> Decimal:
    """Calculate and set total bill from line items (quantity * price_at_order_time)."""
    subtotal = sum(
        (Decimal(item.quantity) * item.price_at_order_time for item in order.order_items),
        start=Decimal("0.00"),
    )
    order.total_bill = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return order.total_bill


def create_order(db: Session, data: OrderCreate) -> Order:
    """Create a new customer order with line items in an atomic transaction."""
    item_ids = [item.menu_item_id for item in data.items]
    menu_items = list(db.scalars(select(MenuItem).where(MenuItem.id.in_(item_ids))).all())
    menu_items_map = {item.id: item for item in menu_items}

    # Verify all menu items exist and are available
    for item_input in data.items:
        menu_item = menu_items_map.get(item_input.menu_item_id)
        if menu_item is None:
            raise ValidationRuleError(
                message=f"Menu item with ID {item_input.menu_item_id} does not exist.",
                code="MENU_ITEM_NOT_FOUND",
            )
        if not menu_item.available:
            raise ValidationRuleError(
                message=f"Menu item '{menu_item.name}' (ID {menu_item.id}) is currently unavailable.",
                code="MENU_ITEM_UNAVAILABLE",
            )

    try:
        order = Order(
            customer_name=data.customer_name,
            table_no=data.table_no,
            status=OrderStatus.PLACED,
            total_bill=Decimal("0.00"),
        )
        db.add(order)
        db.flush()

        order_items = []
        for item_input in data.items:
            menu_item = menu_items_map[item_input.menu_item_id]
            order_item = OrderItem(
                order_id=order.id,
                menu_item_id=menu_item.id,
                quantity=item_input.quantity,
                price_at_order_time=menu_item.price,
            )
            order_items.append(order_item)

        db.add_all(order_items)
        db.flush()

        order.order_items = order_items
        _recalculate_total(order)

        db.commit()
        return get_order(db, order.id)
    except Exception:
        db.rollback()
        raise


def get_order(db: Session, order_id: int) -> Order:
    """Retrieve an order by ID with eagerly loaded line items and menu items."""
    query = (
        select(Order)
        .options(
            selectinload(Order.order_items).selectinload(OrderItem.menu_item)
        )
        .where(Order.id == order_id)
    )
    order = db.scalar(query)
    if order is None:
        raise NotFoundError(
            message=f"Order with ID {order_id} not found.",
            code="ORDER_NOT_FOUND",
        )
    return order


def list_orders(
    db: Session,
    filters: OrderFilter,
    pagination: PaginationParams,
) -> List[Order]:
    """List orders newest first, with optional status/table filters and pagination."""
    query = (
        select(Order)
        .options(
            selectinload(Order.order_items).selectinload(OrderItem.menu_item)
        )
        .order_by(Order.created_at.desc(), Order.id.desc())
    )
    if filters.status is not None:
        query = query.where(Order.status == filters.status)
    if filters.table_no is not None:
        query = query.where(Order.table_no == filters.table_no)

    query = query.offset(pagination.skip).limit(pagination.limit)
    return list(db.scalars(query).all())


def update_item_quantity(
    db: Session,
    order_id: int,
    item_id: int,
    new_quantity: int,
) -> Order:
    """Update line item quantity and recalculate order total bill."""
    order = get_order(db, order_id)
    target_item = None
    for item in order.order_items:
        if item.id == item_id:
            target_item = item
            break

    if target_item is None:
        raise NotFoundError(
            message=f"Order item with ID {item_id} does not belong to Order {order_id}.",
            code="ORDER_ITEM_NOT_FOUND",
        )

    target_item.quantity = new_quantity
    _recalculate_total(order)
    db.commit()
    return get_order(db, order_id)


def update_bill(db: Session, order_id: int, data: BillUpdate) -> Order:
    """Recalculate order total from items, then apply discount and/or service charge."""
    order = get_order(db, order_id)
    subtotal = sum(
        (Decimal(item.quantity) * item.price_at_order_time for item in order.order_items),
        start=Decimal("0.00"),
    )
    total = subtotal

    if data.discount_percent is not None:
        discount = (subtotal * data.discount_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total -= discount

    if data.service_charge_percent is not None:
        service_charge = (subtotal * data.service_charge_percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total += service_charge

    order.total_bill = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    db.commit()
    return get_order(db, order_id)


def cancel_order(db: Session, order_id: int) -> Order:
    """Set an order's status to CANCELLED."""
    order = get_order(db, order_id)
    order.status = OrderStatus.CANCELLED
    db.commit()
    return get_order(db, order_id)


def delete_order(db: Session, order_id: int) -> None:
    """Delete an order and cascade delete its line items."""
    order = get_order(db, order_id)
    db.delete(order)
    db.commit()
