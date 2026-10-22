"""Unit and security tests for deterministic guard rules.

Structured into one test class per rule:
- Rule 1: Kill Switches
- Rule 2: Agent Allowlist
- Rule 3: Session Rate Limit
- Rule 4: Per-Request Action Caps
- Rule 5: Duplicate Calls Prevention
- Rule 6: Provenance Check (Token-based order ID verification)
- Rule 7: Business Rules Pre-check
- Rule 8: Value Limits
- Rule 9: Confirmation Requirement
- Static Check: No LLM imports in guard package
"""

import ast
from pathlib import Path
import pytest
from sqlalchemy.orm import Session
from app.agents.guard.guard import evaluate_call
from app.agents.guard.models import GuardContext, GuardDecision
from app.agents.tools.base import RiskLevel
from app.agents.tools.registry import get_tool
from app.models.enums import OrderStatus
from app.models.menu_item import MenuItem

pytestmark = [pytest.mark.agents, pytest.mark.security]


class TestRule1KillSwitches:
    """Rule 1: Kill switches immediately block writes or destructive tools."""

    def test_writes_kill_switch(self, db: Session, settings_override, seed_menu):
        settings_override(AGENT_WRITES_ENABLED=False)
        tool = get_tool("create_order")
        ctx = GuardContext(agent_name="OrderSpecialist", session_id="s1", request_id="r1", allowed_tools=frozenset({"create_order"}))
        args = {"customer_name": "Test", "table_no": 1, "items": [{"menu_item_id": 1, "quantity": 1}]}

        decision = evaluate_call(tool, args, ctx, db)
        assert decision.outcome == "block"
        assert decision.code == "WRITES_DISABLED"

    def test_destructive_kill_switch(self, db: Session, settings_override, make_order):
        order = make_order()
        settings_override(AGENT_DESTRUCTIVE_ENABLED=False)
        tool = get_tool("cancel_order")
        ctx = GuardContext(
            agent_name="OrderSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"cancel_order"}),
            user_messages=[f"cancel order {order.id}"],
        )

        decision = evaluate_call(tool, {"order_id": order.id}, ctx, db)
        assert decision.outcome == "block"
        assert decision.code == "DESTRUCTIVE_DISABLED"


class TestRule2Allowlist:
    """Rule 2: Tools outside the agent's allowlist are blocked."""

    def test_allowlist_violation(self, db: Session):
        tool = get_tool("create_order")
        ctx = GuardContext(agent_name="BillingSpecialist", session_id="s1", request_id="r1", allowed_tools=frozenset({"get_allowed_actions", "update_bill"}))
        args = {"customer_name": "Test", "table_no": 1, "items": [{"menu_item_id": 1, "quantity": 1}]}

        decision = evaluate_call(tool, args, ctx, db)
        assert decision.outcome == "block"
        assert decision.code == "NOT_IN_ALLOWLIST"


class TestRule3SessionRateLimit:
    """Rule 3: Rapid tool calls within one session are throttled."""

    def test_session_rate_limit(self, db: Session, settings_override):
        settings_override(AGENT_MAX_TOOL_CALLS_PER_MINUTE_PER_SESSION=3)
        tool = get_tool("get_menu")

        for idx in range(3):
            ctx = GuardContext(agent_name="OrderSpecialist", session_id="rate_sess", request_id=f"r_{idx}", allowed_tools=frozenset({"get_menu"}))
            d = evaluate_call(tool, {}, ctx, db)
            assert d.outcome == "allow"

        ctx_blocked = GuardContext(agent_name="OrderSpecialist", session_id="rate_sess", request_id="r_blocked", allowed_tools=frozenset({"get_menu"}))
        d_block = evaluate_call(tool, {}, ctx_blocked, db)
        assert d_block.outcome == "block"
        assert d_block.code == "RATE_LIMIT_EXCEEDED"


class TestRule4PerRequestCaps:
    """Rule 4: Cap maximum writes and destructive actions in one turn."""

    def test_destructive_cap_single_action(self, db: Session, make_order, settings_override):
        o1 = make_order()
        o2 = make_order()
        settings_override(AGENT_MAX_DESTRUCTIVE_PER_REQUEST=1)
        tool = get_tool("cancel_order")
        ctx = GuardContext(
            agent_name="OrderSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"cancel_order"}),
            user_messages=[f"cancel orders {o1.id} and {o2.id}"],
            destructive_used=0,
        )

        d1 = evaluate_call(tool, {"order_id": o1.id}, ctx, db)
        assert d1.outcome == "needs_confirmation"

        ctx.destructive_used = 1
        d2 = evaluate_call(tool, {"order_id": o2.id}, ctx, db)
        assert d2.outcome == "block"
        assert d2.code == "MAX_DESTRUCTIVE_EXCEEDED"


class TestRule5DuplicateCalls:
    """Rule 5: Prevent re-executing identical tool call in the same request."""

    def test_duplicate_identical_call_blocked(self, db: Session, seed_menu):
        tool = get_tool("get_menu")
        ctx = GuardContext(agent_name="OrderSpecialist", session_id="s1", request_id="r1", allowed_tools=frozenset({"get_menu"}))

        d1 = evaluate_call(tool, {}, ctx, db)
        assert d1.outcome == "allow"

        d2 = evaluate_call(tool, {}, ctx, db)
        assert d2.outcome == "block"
        assert d2.code == "DUPLICATE_CALL"


class TestRule6ProvenanceCheck:
    """Rule 6: Target order ID must be explicitly mentioned by the human."""

    def test_provenance_id_in_human_message_passes(self, db: Session, make_order):
        order = make_order()
        tool = get_tool("cancel_order")
        ctx = GuardContext(
            agent_name="OrderSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"cancel_order"}),
            user_messages=[f"Please cancel order {order.id} right away"],
        )

        decision = evaluate_call(tool, {"order_id": order.id}, ctx, db)
        assert decision.outcome == "needs_confirmation"

    def test_provenance_id_not_in_human_message_blocked(self, db: Session, make_order):
        order = make_order()
        tool = get_tool("cancel_order")
        ctx = GuardContext(
            agent_name="OrderSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"cancel_order"}),
            user_messages=["Cancel my last order"],
        )

        decision = evaluate_call(tool, {"order_id": order.id}, ctx, db)
        assert decision.outcome == "block"
        assert decision.code == "PROVENANCE_FAILED"

    def test_provenance_whole_token_matching(self, db: Session, make_order):
        """Verify token '12' does not accidentally match inside '123'."""
        tool = get_tool("cancel_order")
        ctx = GuardContext(
            agent_name="OrderSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"cancel_order"}),
            user_messages=["Table 123 wants cancellation"],
        )

        decision = evaluate_call(tool, {"order_id": 12}, ctx, db)
        assert decision.outcome == "block"


class TestRule7BusinessRulesPrecheck:
    """Rule 7: Enforce domain lifecycle rules before creating confirmation."""

    def test_cancel_preparing_order_blocked_immediately(self, db: Session, make_order):
        order = make_order(status=OrderStatus.PREPARING)
        tool = get_tool("cancel_order")
        ctx = GuardContext(
            agent_name="OrderSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"cancel_order"}),
            user_messages=[f"cancel order {order.id}"],
        )

        decision = evaluate_call(tool, {"order_id": order.id}, ctx, db)
        assert decision.outcome == "block"
        assert "PREPARING" in decision.reason

    def test_missing_order_blocked_immediately(self, db: Session):
        tool = get_tool("cancel_order")
        ctx = GuardContext(
            agent_name="OrderSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"cancel_order"}),
            user_messages=["cancel order 99999"],
        )

        decision = evaluate_call(tool, {"order_id": 99999}, ctx, db)
        assert decision.outcome == "block"
        assert "not found" in decision.reason.lower()


class TestRule8ValueLimits:
    """Rule 8: Guard max discount percentage and max order total."""

    def test_discount_over_cap_blocked(self, db: Session, make_order, settings_override):
        order = make_order()
        settings_override(AGENT_MAX_DISCOUNT_PERCENT=20.0)
        tool = get_tool("update_bill")
        ctx = GuardContext(
            agent_name="BillingSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"update_bill"}),
            user_messages=[f"give 50% discount on order {order.id}"],
        )

        decision = evaluate_call(tool, {"order_id": order.id, "discount_percent": 50.0}, ctx, db)
        assert decision.outcome == "block"
        assert "discount" in decision.reason.lower()


class TestRule9ConfirmationRequirement:
    """Rule 9: DESTRUCTIVE actions require human confirmation; READ/WRITE are allowed."""

    def test_destructive_returns_needs_confirmation(self, db: Session, make_order):
        order = make_order()
        tool = get_tool("cancel_order")
        ctx = GuardContext(
            agent_name="OrderSpecialist",
            session_id="s1",
            request_id="r1",
            allowed_tools=frozenset({"cancel_order"}),
            user_messages=[f"cancel order {order.id}"],
        )

        decision = evaluate_call(tool, {"order_id": order.id}, ctx, db)
        assert decision.outcome == "needs_confirmation"

    def test_read_tool_allowed(self, db: Session, seed_menu):
        tool = get_tool("get_menu")
        ctx = GuardContext(agent_name="OrderSpecialist", session_id="s1", request_id="r1", allowed_tools=frozenset({"get_menu"}))

        decision = evaluate_call(tool, {}, ctx, db)
        assert decision.outcome == "allow"


def test_guard_module_has_zero_llm_imports():
    """Security AST check: Guardrail package must contain ZERO LLM dependencies."""
    guard_dir = Path(__file__).resolve().parent.parent.parent / "backend" / "app" / "agents" / "guard"

    for py_file in guard_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("app.llm") and "groq" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert not node.module.startswith("app.llm") and "groq" not in node.module
