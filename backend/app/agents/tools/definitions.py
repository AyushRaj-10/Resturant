"""Tool handlers and specifications wrapping service functions for AI agents."""

from decimal import Decimal
from typing import Any, Dict, List, Optional
from app.agents.tools.arg_schemas import (
    CancelOrderArgs,
    CreateOrderArgs,
    DeleteOrderArgs,
    GetAllowedActionsArgs,
    GetMenuArgs,
    GetOrderArgs,
    ListOrdersArgs,
    UpdateBillArgs,
    UpdateQuantityArgs,
)
from app.agents.tools.base import RiskLevel, ToolContext, ToolSpec
from app.models.order import Order
from app.schemas.common import OrderFilter, PaginationParams
from app.schemas.order import BillUpdate, OrderCreate
from app.services import menu_service, order_rules, order_service


def _serialize_order(order: Order, allowed_actions: Optional[List[str]] = None) -> Dict[str, Any]:
    """Convert an Order SQLAlchemy model into a clean, JSON-safe dictionary for agents."""
    items_data = []
    for item in order.order_items:
        menu_name = (
            getattr(getattr(item, "menu_item", None), "name", None)
            or f"Item #{item.menu_item_id}"
        )
        line_total = (Decimal(item.quantity) * item.price_at_order_time).quantize(Decimal("0.01"))
        items_data.append({
            "id": item.id,
            "menu_item_id": item.menu_item_id,
            "name": menu_name,
            "quantity": item.quantity,
            "unit_price": f"{item.price_at_order_time:.2f}",
            "line_total": f"{line_total:.2f}",
        })

    data: Dict[str, Any] = {
        "id": order.id,
        "customer_name": order.customer_name,
        "table_no": order.table_no,
        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        "total_bill": f"{order.total_bill:.2f}",
        "discount_percent": f"{order.discount_percent:.2f}" if order.discount_percent is not None else None,
        "service_charge_percent": f"{order.service_charge_percent:.2f}" if order.service_charge_percent is not None else None,
        "items": items_data,
        "created_at": order.created_at.isoformat() if hasattr(order.created_at, "isoformat") else str(order.created_at),
    }
    if allowed_actions is not None:
        data["allowed_actions"] = allowed_actions
    return data


# =========================================================================
# Handlers
# =========================================================================

def get_menu_handler(ctx: ToolContext, args: GetMenuArgs) -> List[Dict[str, Any]]:
    items = menu_service.list_menu_items(ctx.db, only_available=args.only_available)
    return [
        {
            "id": it.id,
            "name": it.name,
            "description": it.description,
            "price": f"{it.price:.2f}",
            "available": it.available,
        }
        for it in items
    ]


def list_orders_handler(ctx: ToolContext, args: ListOrdersArgs) -> List[Dict[str, Any]]:
    filters = OrderFilter(status=args.status, table_no=args.table_no)
    pagination = PaginationParams(skip=0, limit=args.limit)
    orders = order_service.list_orders(ctx.db, filters=filters, pagination=pagination)
    return [
        {
            "id": o.id,
            "customer_name": o.customer_name,
            "table_no": o.table_no,
            "status": o.status.value if hasattr(o.status, "value") else str(o.status),
            "total_bill": f"{o.total_bill:.2f}",
            "item_count": sum(it.quantity for it in o.order_items),
            "created_at": o.created_at.isoformat() if hasattr(o.created_at, "isoformat") else str(o.created_at),
        }
        for o in orders
    ]


def get_order_handler(ctx: ToolContext, args: GetOrderArgs) -> Dict[str, Any]:
    order = order_service.get_order(ctx.db, args.order_id)
    actions = order_rules.get_allowed_actions(order.status)
    return _serialize_order(order, allowed_actions=actions)


def get_allowed_actions_handler(ctx: ToolContext, args: GetAllowedActionsArgs) -> Dict[str, Any]:
    res = order_service.get_allowed_actions_for_order(ctx.db, args.order_id)
    return {
        "order_id": args.order_id,
        "status": res["status"].value if hasattr(res["status"], "value") else str(res["status"]),
        "allowed_actions": res["allowed"],
    }


def create_order_handler(ctx: ToolContext, args: CreateOrderArgs) -> Dict[str, Any]:
    order_create = OrderCreate(
        customer_name=args.customer_name,
        table_no=args.table_no,
        items=args.items,
    )
    order = order_service.create_order(ctx.db, order_create)
    return _serialize_order(order)


def update_quantity_handler(ctx: ToolContext, args: UpdateQuantityArgs) -> Dict[str, Any]:
    order = order_service.update_item_quantity(
        ctx.db,
        order_id=args.order_id,
        item_id=args.item_id,
        new_quantity=args.quantity,
    )
    return _serialize_order(order)


def update_bill_handler(ctx: ToolContext, args: UpdateBillArgs) -> Dict[str, Any]:
    bill_update = BillUpdate(
        discount_percent=args.discount_percent,
        service_charge_percent=args.service_charge_percent,
    )
    order = order_service.update_bill(ctx.db, order_id=args.order_id, data=bill_update)
    return _serialize_order(order)


def cancel_order_handler(ctx: ToolContext, args: CancelOrderArgs) -> Dict[str, Any]:
    order = order_service.cancel_order(ctx.db, order_id=args.order_id)
    return _serialize_order(order)


def delete_order_handler(ctx: ToolContext, args: DeleteOrderArgs) -> Dict[str, Any]:
    order_service.delete_order(ctx.db, order_id=args.order_id)
    return {
        "deleted": True,
        "order_id": args.order_id,
        "message": f"Order #{args.order_id} has been permanently deleted.",
    }


# =========================================================================
# Tool Specifications (9 Tools)
# =========================================================================

TOOL_DEFINITIONS: List[ToolSpec] = [
    ToolSpec(
        name="get_menu",
        description="Retrieve the restaurant menu items, prices, and availability status.",
        args_model=GetMenuArgs,
        risk=RiskLevel.READ,
        handler=get_menu_handler,
    ),
    ToolSpec(
        name="list_orders",
        description="List customer dining orders ordered newest first, with optional status and table filters.",
        args_model=ListOrdersArgs,
        risk=RiskLevel.READ,
        handler=list_orders_handler,
    ),
    ToolSpec(
        name="get_order",
        description="Retrieve detailed information for a single order by ID, including line items, prices, and current status.",
        args_model=GetOrderArgs,
        risk=RiskLevel.READ,
        handler=get_order_handler,
    ),
    ToolSpec(
        name="get_allowed_actions",
        description="Inspect permitted operational actions for an order based on its current lifecycle status.",
        args_model=GetAllowedActionsArgs,
        risk=RiskLevel.READ,
        handler=get_allowed_actions_handler,
    ),
    ToolSpec(
        name="create_order",
        description="Place a new customer dining order with customer name, table number, and line items. Starts in PLACED status.",
        args_model=CreateOrderArgs,
        risk=RiskLevel.WRITE,
        handler=create_order_handler,
    ),
    ToolSpec(
        name="update_quantity",
        description="Update the quantity of a line item in an active PLACED order. Recalculates total bill.",
        args_model=UpdateQuantityArgs,
        risk=RiskLevel.WRITE,
        handler=update_quantity_handler,
    ),
    ToolSpec(
        name="update_bill",
        description="Apply or update discount percentage and/or service charge percentage on an active order. Recalculates total bill.",
        args_model=UpdateBillArgs,
        risk=RiskLevel.WRITE,
        handler=update_bill_handler,
    ),
    ToolSpec(
        name="cancel_order",
        description="Cancel ONE order by ID. Only PLACED orders can be cancelled. This cannot be undone.",
        args_model=CancelOrderArgs,
        risk=RiskLevel.DESTRUCTIVE,
        handler=cancel_order_handler,
        requires_confirmation=True,
    ),
    ToolSpec(
        name="delete_order",
        description="Permanently delete ONE order by ID. Allowed only for terminal orders in CANCELLED or PAID status. This cannot be undone.",
        args_model=DeleteOrderArgs,
        risk=RiskLevel.DESTRUCTIVE,
        handler=delete_order_handler,
        requires_confirmation=True,
    ),
]
