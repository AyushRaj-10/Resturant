"""Unit tests for Pydantic request and response schemas."""

from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas.order import BillUpdate, OrderCreate, OrderItemIn, QuantityUpdate

pytestmark = pytest.mark.unit


def test_order_create_valid():
    """Verify valid OrderCreate schema parses and strips whitespace."""
    data = {
        "customer_name": "  Aarav Sharma  ",
        "table_no": 5,
        "items": [
            {"menu_item_id": 1, "quantity": 2},
            {"menu_item_id": 2, "quantity": 1},
        ],
    }
    order_in = OrderCreate(**data)
    assert order_in.customer_name == "Aarav Sharma"
    assert order_in.table_no == 5
    assert len(order_in.items) == 2
    assert order_in.items[0].menu_item_id == 1
    assert order_in.items[0].quantity == 2


def test_order_create_empty_items():
    """Verify empty items list is rejected."""
    with pytest.raises(ValidationError) as exc:
        OrderCreate(customer_name="Priya", table_no=1, items=[])
    assert "items" in str(exc.value)


@pytest.mark.parametrize("quantity", [0, 51, -1])
def test_order_create_invalid_quantity(quantity: int):
    """Verify quantities <= 0 and > 50 are rejected."""
    with pytest.raises(ValidationError):
        OrderItemIn(menu_item_id=1, quantity=quantity)


def test_order_create_duplicate_items():
    """Verify duplicate menu_item_ids in single order are rejected."""
    data = {
        "customer_name": "Rohan",
        "table_no": 3,
        "items": [
            {"menu_item_id": 1, "quantity": 1},
            {"menu_item_id": 1, "quantity": 2},
        ],
    }
    with pytest.raises(ValidationError) as exc:
        OrderCreate(**data)
    assert "Duplicate menu_item_id" in str(exc.value)


@pytest.mark.parametrize("name", ["", "   ", "\t\n  "])
def test_order_create_blank_customer_name(name: str):
    """Verify empty or whitespace-only customer names are rejected."""
    with pytest.raises(ValidationError) as exc:
        OrderCreate(customer_name=name, table_no=2, items=[{"menu_item_id": 1, "quantity": 1}])
    assert "Customer name cannot be empty or contain only whitespace" in str(exc.value)


@pytest.mark.parametrize("table_no", [0, 201, -5])
def test_order_create_invalid_table_no(table_no: int):
    """Verify tables outside 1..200 range are rejected."""
    with pytest.raises(ValidationError):
        OrderCreate(customer_name="Anita", table_no=table_no, items=[{"menu_item_id": 1, "quantity": 1}])


def test_order_create_unknown_extra_field():
    """Verify unknown extra attributes are strictly forbidden."""
    data = {
        "customer_name": "Anita",
        "table_no": 10,
        "items": [{"menu_item_id": 1, "quantity": 1}],
        "extra_field": "disallowed",
    }
    with pytest.raises(ValidationError) as exc:
        OrderCreate(**data)
    assert "extra_forbidden" in str(exc.value) or "extra_field" in str(exc.value)


def test_bill_update_both_none_rejected():
    """Verify providing neither discount nor service charge is rejected."""
    with pytest.raises(ValidationError) as exc:
        BillUpdate()
    assert "At least one of 'discount_percent' or 'service_charge_percent' must be provided" in str(exc.value)


@pytest.mark.parametrize(
    "discount,service_charge",
    [
        (Decimal("-1.00"), None),
        (Decimal("100.01"), None),
        (None, Decimal("-0.01")),
        (None, Decimal("30.01")),
    ],
)
def test_bill_update_out_of_bounds_percentages(discount, service_charge):
    """Verify negative and over-cap percentages are rejected."""
    with pytest.raises(ValidationError):
        BillUpdate(discount_percent=discount, service_charge_percent=service_charge)


def test_bill_update_valid_decimals():
    """Verify valid percentage decimals up to 2 decimal places."""
    bill = BillUpdate(discount_percent=Decimal("15.50"), service_charge_percent=Decimal("5.00"))
    assert bill.discount_percent == Decimal("15.50")
    assert bill.service_charge_percent == Decimal("5.00")


def test_quantity_update_schema():
    """Verify QuantityUpdate bounds (1..50)."""
    assert QuantityUpdate(quantity=5).quantity == 5
    with pytest.raises(ValidationError):
        QuantityUpdate(quantity=0)
    with pytest.raises(ValidationError):
        QuantityUpdate(quantity=51)
