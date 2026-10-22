"""API integration tests for the /menu endpoints."""

import pytest
from fastapi.testclient import TestClient
from app.models.menu_item import MenuItem

pytestmark = pytest.mark.api


def test_get_menu_empty(client: TestClient):
    """Verify GET /menu returns empty list when no items seeded."""
    resp = client.get("/menu")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_menu_populated(client: TestClient, seed_menu: list[MenuItem]):
    """Verify GET /menu returns all seeded menu items with expected attributes."""
    resp = client.get("/menu")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 6

    names = [i["name"] for i in items]
    assert "Butter Naan" in names
    assert "Paneer Tikka" in names
    assert "Seasonal Fish Fry" in names

    # Check exact price representation
    butter_naan = next(i for i in items if i["name"] == "Butter Naan")
    assert float(butter_naan["price"]) == 50.00
    assert butter_naan["available"] is True

    # Check unavailable item
    fish_fry = next(i for i in items if i["name"] == "Seasonal Fish Fry")
    assert fish_fry["available"] is False
