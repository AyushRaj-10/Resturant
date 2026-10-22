"""Unit and integration tests for Agent tool definitions, schemas, and execution."""

import json
from decimal import Decimal
import pytest
from sqlalchemy.orm import Session
from app.agents.tools.base import RiskLevel, ToolContext, ToolResult
from app.agents.tools.registry import (
    TOOLS,
    execute_tool,
    get_tool,
    list_tools,
    to_llm_tool_specs,
)
from app.models.enums import OrderStatus
from app.models.menu_item import MenuItem
from app.models.order import Order

pytestmark = pytest.mark.agents


def test_registered_tools_count_and_risk_levels():
    """Verify exactly 9 tools are registered with appropriate risk classifications."""
    assert len(TOOLS) == 9

    read_tools = {t.name for t in list_tools(risk=RiskLevel.READ)}
    write_tools = {t.name for t in list_tools(risk=RiskLevel.WRITE)}
    dest_tools = {t.name for t in list_tools(risk=RiskLevel.DESTRUCTIVE)}

    assert read_tools == {"get_menu", "get_order", "list_orders", "get_allowed_actions"}
    assert write_tools == {"create_order", "update_quantity", "update_bill"}
    assert dest_tools == {"cancel_order", "delete_order"}


def test_to_llm_tool_specs_schema_format():
    """Verify generated LLM tool specifications contain no $defs and force additionalProperties=false."""
    specs = to_llm_tool_specs()
    assert len(specs) == 9

    for spec in specs:
        assert spec["type"] == "function"
        fn = spec["function"]
        assert "name" in fn
        assert "description" in fn
        params = fn["parameters"]
        # Verify no unresolved $defs
        assert "$defs" not in params
        assert params.get("additionalProperties") is False


def test_execute_read_tool_success(db: Session, seed_menu: list[MenuItem]):
    """Verify get_menu execution returns structured data."""
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    res = execute_tool(ctx, "get_menu", {})
    assert res.ok is True
    assert res.error is None
    assert len(res.data) >= 5


def test_execute_write_tool_create_order_success(db: Session, seed_menu: list[MenuItem]):
    """Verify create_order execution succeeds and commits new order."""
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    args = {
        "customer_name": "Vikram Seth",
        "table_no": 3,
        "items": [{"menu_item_id": 1, "quantity": 2}],
    }
    res = execute_tool(ctx, "create_order", args)
    assert res.ok is True
    assert res.data["customer_name"] == "Vikram Seth"
    assert res.data["status"] == "PLACED"


def test_execute_tool_invalid_arguments(db: Session):
    """Verify invalid argument types and extra fields return invalid_arguments error without crashing."""
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")

    # Extra disallowed field
    res_extra = execute_tool(ctx, "create_order", {"customer_name": "Test", "table_no": 1, "items": [{"menu_item_id": 1, "quantity": 1}], "hack": True})
    assert res_extra.ok is False
    assert res_extra.error.type == "invalid_arguments"

    # Bad types / empty items
    res_empty = execute_tool(ctx, "create_order", {"customer_name": "Test", "table_no": 1, "items": []})
    assert res_empty.ok is False
    assert res_empty.error.type == "invalid_arguments"


def test_execute_tool_unknown_tool(db: Session):
    """Verify invoking nonexistent tool returns unknown_tool without raising."""
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    res = execute_tool(ctx, "drop_tables_now", {})
    assert res.ok is False
    assert res.error.type == "unknown_tool"


def test_execute_tool_not_found(db: Session):
    """Verify looking up nonexistent order returns not_found."""
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    res = execute_tool(ctx, "get_order", {"order_id": 99999})
    assert res.ok is False
    assert res.error.type == "not_found"


def test_execute_tool_conflict_with_rule_message(db: Session, make_order):
    """Verify modifying quantity on PREPARING order returns conflict error."""
    order = make_order(status=OrderStatus.PREPARING, items=[(1, 1)])
    item_id = order.order_items[0].id

    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    res = execute_tool(ctx, "update_quantity", {"order_id": order.id, "item_id": item_id, "quantity": 4})
    assert res.ok is False
    assert res.error.type in ("conflict", "blocked")
    assert "PREPARING" in res.error.message


def test_no_bulk_arguments_on_destructive_tools(db: Session):
    """Verify bulk argument lists like order_ids are strictly rejected on cancel/delete."""
    ctx = ToolContext(db=db, agent_name="OrderSpecialist", user_messages=["cancel orders 1, 2, 3"])

    res_cancel = execute_tool(ctx, "cancel_order", {"order_ids": [1, 2, 3]})
    assert res_cancel.ok is False
    assert res_cancel.error.type == "invalid_arguments"

    res_delete = execute_tool(ctx, "delete_order", {"order_ids": [1, 2, 3]})
    assert res_delete.ok is False
    assert res_delete.error.type == "invalid_arguments"


def test_db_rollback_after_failed_write(db: Session, make_order, monkeypatch):
    """Verify database transaction rolls back if an exception occurs during write tool execution."""
    order = make_order(items=[(1, 1)])

    def _broken_service(*args, **kwargs):
        raise RuntimeError("Disk write failure")

    monkeypatch.setattr("app.services.order_service.update_item_quantity", _broken_service)

    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    res = execute_tool(
        ctx,
        "update_quantity",
        {"order_id": order.id, "item_id": order.order_items[0].id, "quantity": 5},
    )
    assert res.ok is False
    assert res.error.type == "internal"
    # Ensure session is still usable (rolled back cleanly)
    refreshed = db.query(Order).filter(Order.id == order.id).first()
    assert refreshed.order_items[0].quantity == 1
