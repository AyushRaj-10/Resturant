"""API integration tests for order lifecycle, operations, errors, and allowed actions."""

from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.enums import OrderStatus
from app.models.menu_item import MenuItem
from app.models.order import Order

pytestmark = pytest.mark.api


# =========================================================================
# Order Creation & Price Snapshot Tests
# =========================================================================

def test_create_order_success(client: TestClient, db: Session, seed_menu: list[MenuItem]):
    """Verify order creation calculates exact total_bill and snapshots unit prices."""
    # 2 x Butter Naan (50.00) + 1 x Paneer Tikka (250.00) = 350.00
    payload = {
        "customer_name": "Rohan Gupta",
        "table_no": 5,
        "items": [
            {"menu_item_id": 1, "quantity": 2},
            {"menu_item_id": 2, "quantity": 1},
        ],
    }
    resp = client.post("/orders", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["customer_name"] == "Rohan Gupta"
    assert data["table_no"] == 5
    assert data["status"] == "PLACED"
    assert float(data["total_bill"]) == 350.00
    assert len(data["items"]) == 2

    # Verify price snapshotting: mutate menu item price and verify order total is unaffected
    naan = db.query(MenuItem).filter(MenuItem.id == 1).first()
    naan.price = Decimal("999.00")
    db.commit()

    order_resp = client.get(f"/orders/{data['id']}")
    assert order_resp.status_code == 200
    assert float(order_resp.json()["total_bill"]) == 350.00


def test_create_order_unknown_item_returns_400(client: TestClient, db: Session, seed_menu: list[MenuItem]):
    """Verify unknown item returns 400 and nothing is persisted."""
    payload = {
        "customer_name": "Ghost Customer",
        "table_no": 1,
        "items": [{"menu_item_id": 99999, "quantity": 1}],
    }
    resp = client.post("/orders", json=payload)
    assert resp.status_code == 400
    err = resp.json()
    assert "detail" in err and "code" in err

    # Confirm no partial order persisted
    assert db.query(Order).count() == 0


def test_create_order_unavailable_item_returns_400(client: TestClient, db: Session, seed_menu: list[MenuItem]):
    """Verify ordering unavailable item returns 400 and nothing is persisted."""
    # Item 6 is Seasonal Fish Fry (available=False)
    payload = {
        "customer_name": "Priya",
        "table_no": 2,
        "items": [{"menu_item_id": 6, "quantity": 1}],
    }
    resp = client.post("/orders", json=payload)
    assert resp.status_code == 400
    assert "unavailable" in resp.json()["detail"].lower()
    assert db.query(Order).count() == 0


# =========================================================================
# Order Querying & Pagination Tests
# =========================================================================

def test_list_orders_filtering_and_sorting(client: TestClient, make_order):
    """Verify filters (status, table_no), pagination (skip, limit), and newest-first order."""
    o1 = make_order(customer_name="Customer 1", table_no=1, status=OrderStatus.PLACED)
    o2 = make_order(customer_name="Customer 2", table_no=2, status=OrderStatus.PREPARING)
    o3 = make_order(customer_name="Customer 3", table_no=1, status=OrderStatus.SERVED)

    # Newest first
    resp = client.get("/orders")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["id"] == o3.id
    assert data[1]["id"] == o2.id
    assert data[2]["id"] == o1.id

    # Filter by table_no
    resp_t1 = client.get("/orders?table_no=1")
    assert resp_t1.status_code == 200
    ids_t1 = [o["id"] for o in resp_t1.json()]
    assert ids_t1 == [o3.id, o1.id]

    # Filter by status
    resp_prep = client.get("/orders?status=PREPARING")
    assert resp_prep.status_code == 200
    assert len(resp_prep.json()) == 1
    assert resp_prep.json()[0]["id"] == o2.id

    # Pagination: limit=1, skip=1
    resp_page = client.get("/orders?limit=1&skip=1")
    assert resp_page.status_code == 200
    page_data = resp_page.json()
    assert len(page_data) == 1
    assert page_data[0]["id"] == o2.id


def test_get_order_by_id_and_missing_id(client: TestClient, make_order):
    """Verify get by ID, 404 for missing ID, and 422 for non-positive ID."""
    order = make_order()

    # Success
    resp = client.get(f"/orders/{order.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == order.id

    # 404 for missing
    resp_404 = client.get("/orders/999999")
    assert resp_404.status_code == 404
    assert "detail" in resp_404.json()

    # 422 for non-positive ID
    resp_422 = client.get("/orders/0")
    assert resp_422.status_code == 422


# =========================================================================
# Item Quantity Update Tests
# =========================================================================

def test_update_item_quantity_success_recalculates_total(client: TestClient, make_order):
    """Verify quantity update recalculates total bill."""
    # 2 x Naan (50.00) = 100.00
    order = make_order(items=[(1, 2)])
    item_id = order.order_items[0].id

    # Change quantity to 4 -> total becomes 200.00
    resp = client.patch(f"/orders/{order.id}/items/{item_id}", json={"quantity": 4})
    assert resp.status_code == 200
    data = resp.json()
    assert float(data["total_bill"]) == 200.00
    assert data["items"][0]["quantity"] == 4


def test_update_item_quantity_wrong_order_gives_404(client: TestClient, make_order):
    """Verify updating item with mismatching order ID returns 404."""
    order1 = make_order(customer_name="O1", items=[(1, 1)])
    order2 = make_order(customer_name="O2", items=[(2, 1)])
    o1_item_id = order1.order_items[0].id

    resp = client.patch(f"/orders/{order2.id}/items/{o1_item_id}", json={"quantity": 3})
    assert resp.status_code == 404


def test_update_item_quantity_blocked_after_preparing(client: TestClient, make_order):
    """Verify updating item quantity on PREPARING order returns 409."""
    order = make_order(status=OrderStatus.PREPARING, items=[(1, 2)])
    item_id = order.order_items[0].id

    resp = client.patch(f"/orders/{order.id}/items/{item_id}", json={"quantity": 3})
    assert resp.status_code == 409
    assert "PREPARING" in resp.json()["detail"]


# =========================================================================
# Bill Update Tests
# =========================================================================

def test_update_bill_calculations_and_idempotency(client: TestClient, make_order):
    """Verify ROUND_HALF_UP calculations and that re-applying same bill update does not compound."""
    # 1 x Paneer Tikka (250.00)
    order = make_order(items=[(2, 1)])

    # Apply 10% discount and 5% service charge
    # Subtotal: 250.00
    # Discount: 25.00 -> 225.00
    # Service charge: 12.50
    # Total: 237.50
    payload = {"discount_percent": "10.00", "service_charge_percent": "5.00"}
    resp1 = client.patch(f"/orders/{order.id}/bill", json=payload)
    assert resp1.status_code == 200
    assert float(resp1.json()["total_bill"]) == 237.50

    # Repeat call: total must remain 237.50 (not compound)
    resp2 = client.patch(f"/orders/{order.id}/bill", json=payload)
    assert resp2.status_code == 200
    assert float(resp2.json()["total_bill"]) == 237.50


def test_update_bill_blocked_on_terminal_order(client: TestClient, make_order):
    """Verify updating bill on PAID or CANCELLED order returns 409."""
    order = make_order(status=OrderStatus.PAID)
    resp = client.patch(f"/orders/{order.id}/bill", json={"discount_percent": "5.00"})
    assert resp.status_code == 409


# =========================================================================
# Status Transition, Cancel, and Delete Tests
# =========================================================================

def test_status_endpoint_transitions(client: TestClient, make_order):
    """Verify valid transitions succeed and invalid jumps return 409."""
    order = make_order(status=OrderStatus.PLACED)

    # Valid: PLACED -> PREPARING
    r1 = client.post(f"/orders/{order.id}/status", json={"status": "PREPARING"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "PREPARING"

    # Invalid jump: PREPARING -> PAID returns 409
    r2 = client.post(f"/orders/{order.id}/status", json={"status": "PAID"})
    assert r2.status_code == 409


def test_cancel_order_rules(client: TestClient, make_order):
    """Verify only PLACED orders can be cancelled, second cancel returns 409."""
    order = make_order(status=OrderStatus.PLACED)

    # First cancel succeeds
    r1 = client.post(f"/orders/{order.id}/status", json={"status": "CANCELLED"})
    assert r1.status_code == 200
    assert r1.json()["status"] == "CANCELLED"

    # Second cancel returns 409
    r2 = client.post(f"/orders/{order.id}/status", json={"status": "CANCELLED"})
    assert r2.status_code == 409


def test_delete_order_rules(client: TestClient, make_order):
    """Verify delete is allowed only for CANCELLED or PAID, blocked for PLACED/PREPARING."""
    # PLACED -> 409
    o_placed = make_order(status=OrderStatus.PLACED)
    assert client.delete(f"/orders/{o_placed.id}").status_code == 409

    # PREPARING -> 409
    o_prep = make_order(status=OrderStatus.PREPARING)
    assert client.delete(f"/orders/{o_prep.id}").status_code == 409

    # CANCELLED -> 200/204
    o_canc = make_order(status=OrderStatus.CANCELLED)
    assert client.delete(f"/orders/{o_canc.id}").status_code in (200, 204)

    # PAID -> 200/204
    o_paid = make_order(status=OrderStatus.PAID)
    assert client.delete(f"/orders/{o_paid.id}").status_code in (200, 204)


def test_allowed_actions_endpoint(client: TestClient, make_order):
    """Verify allowed-actions endpoint correctly reflects permitted rules for each status."""
    o_placed = make_order(status=OrderStatus.PLACED)
    resp = client.get(f"/orders/{o_placed.id}/allowed-actions")
    assert resp.status_code == 200
    allowed = resp.json()["allowed"]
    assert "update_quantity" in allowed
    assert "cancel" in allowed
    assert "delete" not in allowed

    o_canc = make_order(status=OrderStatus.CANCELLED)
    resp_canc = client.get(f"/orders/{o_canc.id}/allowed-actions")
    assert resp_canc.status_code == 200
    allowed_canc = resp_canc.json()["allowed"]
    assert "delete" in allowed_canc
    assert "cancel" not in allowed_canc
    assert "update_quantity" not in allowed_canc


def test_clean_500_on_unexpected_exception(monkeypatch):
    """Verify unhandled exceptions return a clean 500 error with no SQL or stack trace."""
    from app.main import app as fastapi_app

    def _exploding_service(*args, **kwargs):
        raise RuntimeError("CRITICAL DATABASE CORRUPTION: SELECT * FROM mysql.user WHERE user='root'")

    monkeypatch.setattr("app.services.order_service.list_orders", _exploding_service)
    with TestClient(fastapi_app, raise_server_exceptions=False) as err_client:
        resp = err_client.get("/orders")
        assert resp.status_code == 500
        data = resp.json()
        assert data["code"] == "INTERNAL_SERVER_ERROR"
        assert "unexpected" in data["detail"]
        assert "mysql" not in data["detail"]
        assert "Traceback" not in data["detail"]
