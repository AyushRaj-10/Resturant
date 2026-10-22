from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.audit import AgentAuditLog
from app.models.enums import AuditDecision, OrderStatus
from app.models.menu_item import MenuItem
from app.models.order import Order, OrderItem


def test_create_and_read_models(db_session: Session):
    """Test creating MenuItem, Order, and OrderItem and querying them back."""
    # Create MenuItem
    menu_item = MenuItem(
        name="Paneer Tikka",
        description="Marinated cottage cheese grilled in tandoor",
        price=Decimal("260.00"),
        available=True,
    )
    db_session.add(menu_item)
    db_session.commit()
    db_session.refresh(menu_item)

    assert menu_item.id is not None
    assert menu_item.name == "Paneer Tikka"

    # Create Order with OrderItem
    order = Order(
        customer_name="Aarav Sharma",
        table_no=4,
        total_bill=Decimal("520.00"),
    )
    order_item = OrderItem(
        order=order,
        menu_item=menu_item,
        quantity=2,
        price_at_order_time=Decimal("260.00"),
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    # Read back
    retrieved_order = db_session.scalar(select(Order).where(Order.id == order.id))
    assert retrieved_order is not None
    assert retrieved_order.customer_name == "Aarav Sharma"
    assert retrieved_order.table_no == 4
    assert len(retrieved_order.order_items) == 1

    retrieved_item = retrieved_order.order_items[0]
    assert retrieved_item.quantity == 2
    assert retrieved_item.price_at_order_time == Decimal("260.00")
    assert retrieved_item.menu_item.name == "Paneer Tikka"


def test_default_order_status(db_session: Session):
    """Verify that an order defaults to PLACED status if not explicitly set."""
    order = Order(
        customer_name="Priya Patel",
        table_no=7,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)

    assert order.status == OrderStatus.PLACED


def test_cascade_delete_order(db_session: Session):
    """Verify deleting an Order cascades and removes associated OrderItems without deleting the MenuItem."""
    menu_item = MenuItem(
        name="Butter Naan",
        price=Decimal("55.00"),
    )
    db_session.add(menu_item)
    db_session.commit()

    order = Order(
        customer_name="Vikram Singh",
        table_no=2,
    )
    order_item = OrderItem(
        order=order,
        menu_item=menu_item,
        quantity=3,
        price_at_order_time=Decimal("55.00"),
    )
    db_session.add(order)
    db_session.commit()

    order_id = order.id
    order_item_id = order_item.id
    menu_item_id = menu_item.id

    # Delete order
    db_session.delete(order)
    db_session.commit()

    # Associated OrderItem must be deleted
    assert db_session.scalar(select(OrderItem).where(OrderItem.id == order_item_id)) is None

    # Underlying MenuItem must remain intact
    surviving_menu_item = db_session.scalar(select(MenuItem).where(MenuItem.id == menu_item_id))
    assert surviving_menu_item is not None
    assert surviving_menu_item.name == "Butter Naan"


def test_check_constraints_price_and_quantity(db_session: Session):
    """Verify that price <= 0 and quantity <= 0 are rejected by database check constraints."""
    # Test MenuItem price == 0
    with pytest.raises(IntegrityError):
        db_session.add(MenuItem(name="Zero Price Item", price=Decimal("0.00")))
        db_session.commit()
    db_session.rollback()

    # Test MenuItem price < 0
    with pytest.raises(IntegrityError):
        db_session.add(MenuItem(name="Negative Price Item", price=Decimal("-10.00")))
        db_session.commit()
    db_session.rollback()

    # Prepare valid MenuItem and Order for testing OrderItem constraints
    valid_menu_item = MenuItem(name="Dal Tadka", price=Decimal("180.00"))
    valid_order = Order(customer_name="Karan", table_no=1)
    db_session.add_all([valid_menu_item, valid_order])
    db_session.commit()

    # Test OrderItem quantity == 0
    with pytest.raises(IntegrityError):
        db_session.add(
            OrderItem(
                order=valid_order,
                menu_item=valid_menu_item,
                quantity=0,
                price_at_order_time=Decimal("180.00"),
            )
        )
        db_session.commit()
    db_session.rollback()

    # Test OrderItem quantity < 0
    with pytest.raises(IntegrityError):
        db_session.add(
            OrderItem(
                order=valid_order,
                menu_item=valid_menu_item,
                quantity=-2,
                price_at_order_time=Decimal("180.00"),
            )
        )
        db_session.commit()
    db_session.rollback()


def test_agent_audit_log_with_json(db_session: Session):
    """Verify that AgentAuditLog rows can be created, stored, and read with JSON arguments and results."""
    audit_entry = AgentAuditLog(
        agent_name="OrderGuardAgent",
        tool_name="cancel_order",
        arguments={"order_id": 101, "reason": "Customer request"},
        decision=AuditDecision.ALLOWED,
        reason="Order is in PLACED status and eligible for cancellation",
        result={"status": "cancelled", "refund_required": False},
    )
    db_session.add(audit_entry)
    db_session.commit()
    db_session.refresh(audit_entry)

    assert audit_entry.id is not None
    assert audit_entry.agent_name == "OrderGuardAgent"
    assert audit_entry.tool_name == "cancel_order"
    assert audit_entry.decision == AuditDecision.ALLOWED
    assert audit_entry.arguments == {"order_id": 101, "reason": "Customer request"}
    assert audit_entry.result == {"status": "cancelled", "refund_required": False}
    assert audit_entry.created_at is not None
