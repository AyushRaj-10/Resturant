"""Integration and security tests for the human confirmation lifecycle."""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.agents.guard.confirmations import confirmations_store
from app.models.enums import AuditDecision, OrderStatus
from app.models.order import Order

pytestmark = [pytest.mark.agents, pytest.mark.security]


def test_propose_then_approve_cancels_order(client: TestClient, db: Session, make_order):
    """Verify proposing a cancel action and approving it changes order status to CANCELLED."""
    order = make_order(status=OrderStatus.PLACED)
    session_id = "test_user_sess_1"

    # Create pending action in store
    action = confirmations_store.create_pending_action(
        session_id=session_id,
        agent_name="OrderSpecialist",
        tool_name="cancel_order",
        arguments={"order_id": order.id},
        summary=f"Cancel Order #{order.id}",
        snapshot={"status": "PLACED", "total_bill": str(order.total_bill)},
    )

    # Approve action
    resp = client.post(
        "/agent/confirm",
        json={"confirmation_id": action.confirmation_id, "session_id": session_id, "approve": True},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Check order was cancelled in DB
    db.refresh(order)
    assert order.status == OrderStatus.CANCELLED


def test_propose_then_reject_leaves_order_unchanged(client: TestClient, db: Session, make_order):
    """Verify rejecting a confirmation leaves the order unchanged."""
    order = make_order(status=OrderStatus.PLACED)
    session_id = "test_user_sess_2"

    action = confirmations_store.create_pending_action(
        session_id=session_id,
        agent_name="OrderSpecialist",
        tool_name="cancel_order",
        arguments={"order_id": order.id},
        summary=f"Cancel Order #{order.id}",
        snapshot={"status": "PLACED", "total_bill": str(order.total_bill)},
    )

    resp = client.post(
        "/agent/confirm",
        json={"confirmation_id": action.confirmation_id, "session_id": session_id, "approve": False},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False

    # Check order is still PLACED
    db.refresh(order)
    assert order.status == OrderStatus.PLACED


def test_reuse_of_consumed_confirmation_id_refused(client: TestClient, db: Session, make_order):
    """Verify a consumed confirmation token cannot be reused (single-use enforcement)."""
    order = make_order()
    session_id = "test_user_sess_3"

    action = confirmations_store.create_pending_action(
        session_id=session_id,
        agent_name="OrderSpecialist",
        tool_name="cancel_order",
        arguments={"order_id": order.id},
        summary=f"Cancel Order #{order.id}",
        snapshot={"status": "PLACED", "total_bill": str(order.total_bill)},
    )

    # First approve succeeds
    r1 = client.post(
        "/agent/confirm",
        json={"confirmation_id": action.confirmation_id, "session_id": session_id, "approve": True},
    )
    assert r1.status_code == 200

    # Second approve fails with 409 Conflict
    r2 = client.post(
        "/agent/confirm",
        json={"confirmation_id": action.confirmation_id, "session_id": session_id, "approve": True},
    )
    assert r2.status_code == 409


def test_expired_confirmation_refused_via_fake_clock(client: TestClient, db: Session, make_order, fake_clock):
    """Verify advancing controllable clock past TTL causes confirmation to expire and return 410."""
    order = make_order()
    session_id = "test_user_sess_4"

    action = confirmations_store.create_pending_action(
        session_id=session_id,
        agent_name="OrderSpecialist",
        tool_name="cancel_order",
        arguments={"order_id": order.id},
        summary=f"Cancel Order #{order.id}",
        snapshot={"status": "PLACED", "total_bill": str(order.total_bill)},
        ttl_seconds=60,
    )

    # Advance clock by 120 seconds
    fake_clock.advance(120)

    resp = client.post(
        "/agent/confirm",
        json={"confirmation_id": action.confirmation_id, "session_id": session_id, "approve": True},
    )
    assert resp.status_code == 410
    assert "expired" in resp.json()["detail"].lower()


def test_cross_session_and_guessed_confirmation_refused(client: TestClient, db: Session, make_order):
    """Verify mismatched session returns 403, and guessed or random token returns 404."""
    order = make_order()
    action = confirmations_store.create_pending_action(
        session_id="session_A",
        agent_name="OrderSpecialist",
        tool_name="cancel_order",
        arguments={"order_id": order.id},
        summary=f"Cancel Order #{order.id}",
        snapshot={"status": "PLACED", "total_bill": str(order.total_bill)},
    )

    # Session B tries to confirm Session A's action -> 403 Forbidden
    r_cross = client.post(
        "/agent/confirm",
        json={"confirmation_id": action.confirmation_id, "session_id": "session_B", "approve": True},
    )
    assert r_cross.status_code == 403

    # Guessed random token -> 404 Not Found
    r_guess = client.post(
        "/agent/confirm",
        json={"confirmation_id": "completely_fake_token_12345", "session_id": "session_A", "approve": True},
    )
    assert r_guess.status_code == 404


def test_state_changed_between_propose_and_approve_refused(client: TestClient, db: Session, make_order):
    """Verify if order status or total changes before approval, confirmation is aborted with 409."""
    order = make_order(status=OrderStatus.PLACED)
    session_id = "test_state_change_sess"

    action = confirmations_store.create_pending_action(
        session_id=session_id,
        agent_name="OrderSpecialist",
        tool_name="cancel_order",
        arguments={"order_id": order.id},
        summary=f"Cancel Order #{order.id}",
        snapshot={"status": "PLACED", "total_bill": str(order.total_bill)},
    )

    # Kitchen starts preparing order in the meantime!
    order.status = OrderStatus.PREPARING
    db.commit()

    # User attempts to confirm -> must be rejected because PREPARING cannot be cancelled
    resp = client.post(
        "/agent/confirm",
        json={"confirmation_id": action.confirmation_id, "session_id": session_id, "approve": True},
    )
    assert resp.status_code == 409
    assert "PREPARING" in resp.json()["detail"] or "Cannot cancel" in resp.json()["detail"]


def test_confirmation_token_length_and_randomness():
    """Verify confirmation tokens are high-entropy and unguessable."""
    tokens = {confirmations_store.create_pending_action("s", "a", "t", {}, "sum", {}).confirmation_id for _ in range(50)}
    assert len(tokens) == 50
    for tok in tokens:
        assert len(tok) >= 20


def test_list_pending_scoped_to_session(client: TestClient, make_order):
    """Verify /agent/pending only lists active pending actions belonging to the requesting session."""
    o1 = make_order()
    o2 = make_order()

    a1 = confirmations_store.create_pending_action("sess_1", "OrderSpecialist", "cancel_order", {"order_id": o1.id}, "Cancel 1", {})
    a2 = confirmations_store.create_pending_action("sess_2", "OrderSpecialist", "cancel_order", {"order_id": o2.id}, "Cancel 2", {})

    resp = client.get("/agent/pending?session_id=sess_1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["confirmation_id"] == a1.confirmation_id
