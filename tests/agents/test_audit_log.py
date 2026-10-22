"""Unit and security tests for immutable, fail-closed audit logging."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.agents.guard.audit import log_decision
from app.agents.tools.base import RiskLevel, ToolContext
from app.agents.tools.registry import execute_tool
from app.models.audit import AgentAuditLog
from app.models.enums import AuditDecision
from app.main import app as fastapi_app

pytestmark = [pytest.mark.agents, pytest.mark.security]


def test_audit_logs_every_decision_type(db: Session):
    """Verify ALLOWED, BLOCKED, and PENDING_CONFIRMATION rows are persisted accurately."""
    log_decision("OrderSpecialist", "get_menu", {}, AuditDecision.ALLOWED, "Read allowed", session_id="s1")
    log_decision("BillingSpecialist", "create_order", {}, AuditDecision.BLOCKED, "Allowlist violation", session_id="s2")
    log_decision("OrderSpecialist", "cancel_order", {"order_id": 1}, AuditDecision.PENDING_CONFIRMATION, "Pending confirmation", session_id="s3")

    rows = db.query(AgentAuditLog).all()
    decisions = {r.decision for r in rows}
    assert decisions == {AuditDecision.ALLOWED, AuditDecision.BLOCKED, AuditDecision.PENDING_CONFIRMATION}


def test_audit_row_survives_rolled_back_tool_transaction(db: Session, make_order, monkeypatch):
    """Verify audit log row persists even when tool transaction rolls back."""
    order = make_order()

    def _exploding_service(*args, **kwargs):
        raise RuntimeError("Unexpected DB failure inside service")

    monkeypatch.setattr("app.services.order_service.update_item_quantity", _exploding_service)

    ctx = ToolContext(db=db, agent_name="OrderSpecialist", session_id="sess_rollback")
    res = execute_tool(ctx, "update_quantity", {"order_id": order.id, "item_id": order.order_items[0].id, "quantity": 5})
    assert res.ok is False

    # The tool failed and rolled back, but audit log must be saved
    audit_rows = db.query(AgentAuditLog).filter(AgentAuditLog.tool_name == "update_quantity").all()
    assert len(audit_rows) >= 1


def test_fail_closed_audit_policy(db: Session, monkeypatch):
    """Verify that if audit log write fails, WRITE and DESTRUCTIVE tools are blocked, while READ proceeds."""
    def _exploding_audit(*args, **kwargs):
        raise RuntimeError("Audit log storage unreachable")

    monkeypatch.setattr("app.agents.guard.audit.log_decision", _exploding_audit)

    ctx = ToolContext(db=db, agent_name="OrderSpecialist")

    # 1. READ tool proceeds despite audit failure
    res_read = execute_tool(ctx, "get_menu", {})
    assert res_read.ok is True

    # 2. WRITE tool fails closed
    res_write = execute_tool(ctx, "create_order", {"customer_name": "Test", "table_no": 1, "items": [{"menu_item_id": 1, "quantity": 1}]})
    assert res_write.ok is False
    assert "audit" in res_write.error.message.lower()


def test_audit_metadata_and_truncation(db: Session):
    """Verify request_id, session_id, and long string truncation in audit logs."""
    long_arg = "A" * 500
    log_decision(
        agent_name="OrderSpecialist",
        tool_name="test_tool",
        arguments={"input": long_arg},
        decision=AuditDecision.ALLOWED,
        reason="Test truncation",
        session_id="my_sess",
        request_id="my_req",
    )

    row = db.query(AgentAuditLog).filter(AgentAuditLog.tool_name == "test_tool").first()
    assert row is not None
    assert row.arguments["_meta"]["session_id"] == "my_sess"
    assert row.arguments["_meta"]["request_id"] == "my_req"
    assert len(row.arguments["input"]) <= 220
    assert "... [truncated]" in row.arguments["input"]


def test_get_audit_log_endpoint_filters_and_pagination(client: TestClient, db: Session):
    """Verify GET /agent/audit-log pagination and filters."""
    log_decision("OrderSpecialist", "get_menu", {}, AuditDecision.ALLOWED, "ok")
    log_decision("OrderSpecialist", "cancel_order", {}, AuditDecision.BLOCKED, "blocked")
    log_decision("BillingSpecialist", "update_bill", {}, AuditDecision.ALLOWED, "ok")

    # Filter by decision
    r_blocked = client.get("/agent/audit-log?decision=BLOCKED")
    assert r_blocked.status_code == 200
    assert len(r_blocked.json()) == 1
    assert r_blocked.json()[0]["decision"] == "BLOCKED"

    # Filter by agent
    r_agent = client.get("/agent/audit-log?agent_name=BillingSpecialist")
    assert r_agent.status_code == 200
    assert len(r_agent.json()) == 1

    # Pagination
    r_page = client.get("/agent/audit-log?limit=2&skip=0")
    assert r_page.status_code == 200
    assert len(r_page.json()) == 2


def test_no_mutating_routes_for_audit_log():
    """Verify no PUT, PATCH, or DELETE routes exist on audit paths (immutability check)."""
    for route in fastapi_app.routes:
        path = getattr(route, "path", "")
        if "audit" in path:
            methods = getattr(route, "methods", set())
            for m in ("POST", "PUT", "PATCH", "DELETE"):
                assert m not in methods, f"Mutating method {m} forbidden on audit route: {path}"
