"""Integration tests for application health check endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app as fastapi_app

pytestmark = pytest.mark.api


def test_health(client: TestClient):
    """Verify that GET /health returns 200 and {'status': 'ok'}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_reachable(client: TestClient):
    """Verify /health/db reports healthy connectivity to database."""
    response = client.get("/health/db")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "reachable"


def test_health_db_unreachable_on_failure(monkeypatch):
    """Verify /health/db returns 503 with error detail when database connectivity fails."""
    def _broken_execute(*args, **kwargs):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(Session, "execute", _broken_execute)
    with TestClient(fastapi_app, raise_server_exceptions=False) as tc:
        response = tc.get("/health/db")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "error"
        assert data["database"] == "unreachable"
