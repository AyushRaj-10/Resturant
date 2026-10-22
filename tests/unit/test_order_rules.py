"""Unit tests for pure order lifecycle business rules and operational guards."""

import pytest
from app.models.enums import OrderStatus
from app.services.order_rules import (
    ALLOWED_TRANSITIONS,
    Operation,
    can_cancel,
    can_delete,
    can_transition,
    can_update_bill,
    can_update_quantity,
    explain_block,
)

pytestmark = pytest.mark.unit


# =========================================================================
# Operation Permission Table Tests
# =========================================================================

@pytest.mark.parametrize(
    "status,expected",
    [
        (OrderStatus.PLACED, True),
        (OrderStatus.PREPARING, False),
        (OrderStatus.SERVED, False),
        (OrderStatus.PAID, False),
        (OrderStatus.CANCELLED, False),
    ],
)
def test_can_update_quantity_rule_table(status: OrderStatus, expected: bool):
    """Verify item quantity changes are strictly permitted only when order is PLACED."""
    assert can_update_quantity(status) is expected


@pytest.mark.parametrize(
    "status,expected",
    [
        (OrderStatus.PLACED, True),
        (OrderStatus.PREPARING, True),
        (OrderStatus.SERVED, True),
        (OrderStatus.PAID, False),
        (OrderStatus.CANCELLED, False),
    ],
)
def test_can_update_bill_rule_table(status: OrderStatus, expected: bool):
    """Verify bill updates permitted in active states (PLACED, PREPARING, SERVED)."""
    assert can_update_bill(status) is expected


@pytest.mark.parametrize(
    "status,expected",
    [
        (OrderStatus.PLACED, True),
        (OrderStatus.PREPARING, False),
        (OrderStatus.SERVED, False),
        (OrderStatus.PAID, False),
        (OrderStatus.CANCELLED, False),
    ],
)
def test_can_cancel_rule_table(status: OrderStatus, expected: bool):
    """Verify cancellation is strictly restricted to PLACED status."""
    assert can_cancel(status) is expected


@pytest.mark.parametrize(
    "status,expected",
    [
        (OrderStatus.PLACED, False),
        (OrderStatus.PREPARING, False),
        (OrderStatus.SERVED, False),
        (OrderStatus.PAID, True),
        (OrderStatus.CANCELLED, True),
    ],
)
def test_can_delete_rule_table(status: OrderStatus, expected: bool):
    """Verify deletion permitted only for terminal statuses (PAID or CANCELLED)."""
    assert can_delete(status) is expected


# =========================================================================
# Lifecycle State Transition Tests
# =========================================================================

def test_all_status_transition_pairs():
    """Exhaustive table-driven test of every possible (current, target) status pair."""
    all_statuses = list(OrderStatus)

    for current in all_statuses:
        allowed_targets = ALLOWED_TRANSITIONS.get(current, set())
        for target in all_statuses:
            is_valid = can_transition(current, target)
            if target in allowed_targets:
                assert is_valid is True, f"Expected {current.value} -> {target.value} to be ALLOWED"
            else:
                assert is_valid is False, f"Expected {current.value} -> {target.value} to be BLOCKED"


def test_terminal_statuses_have_no_transitions():
    """Verify terminal statuses (PAID, CANCELLED) have zero allowed outbound transitions."""
    assert len(ALLOWED_TRANSITIONS[OrderStatus.PAID]) == 0
    assert len(ALLOWED_TRANSITIONS[OrderStatus.CANCELLED]) == 0


# =========================================================================
# Block Explanation Tests
# =========================================================================

def test_explain_block_cancel():
    """Verify explain_block on cancel names status and provides clean explanation."""
    msg = explain_block(Operation.CANCEL, OrderStatus.PREPARING, order_id=42)
    assert "Order 42 cannot be cancelled because it is already PREPARING" in msg
    assert "Only PLACED orders can be cancelled" in msg

    msg_already = explain_block(Operation.CANCEL, OrderStatus.CANCELLED, order_id=42)
    assert "Order 42 is already CANCELLED" in msg_already


def test_explain_block_update_quantity():
    """Verify explain_block on quantity modification."""
    msg = explain_block(Operation.UPDATE_QUANTITY, OrderStatus.SERVED, order_id=10)
    assert "Order 10 item quantity cannot be updated because its status is SERVED" in msg


def test_explain_block_update_bill():
    """Verify explain_block on bill modification."""
    msg = explain_block(Operation.UPDATE_BILL, OrderStatus.PAID, order_id=15)
    assert "Order 15 bill adjustments cannot be applied because its status is PAID" in msg


def test_explain_block_delete():
    """Verify explain_block on deletion of active order."""
    msg = explain_block(Operation.DELETE, OrderStatus.PLACED, order_id=7)
    assert "Order 7 cannot be deleted because its status is PLACED" in msg
    assert "Only CANCELLED or PAID orders can be deleted" in msg


def test_explain_block_invalid_status_transition():
    """Verify explain_block on invalid status jump."""
    msg = explain_block(Operation.CHANGE_STATUS, OrderStatus.PLACED, target_status=OrderStatus.PAID, order_id=3)
    assert "Order 3" in msg
    assert "PAID" in msg

    msg_terminal = explain_block(Operation.CHANGE_STATUS, OrderStatus.CANCELLED, target_status=OrderStatus.PLACED, order_id=3)
    assert "terminal status CANCELLED" in msg_terminal
