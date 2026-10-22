"""Integration tests for the Agent Runner, Router, and Orchestrator loop."""

import json
import pytest
from sqlalchemy.orm import Session
from app.agents.base import AgentRunResult
from app.agents.billing_agent import BILLING_AGENT_SPEC
from app.agents.groq_tools_client import ChatCompletionResult, ToolCallRaw
from app.agents.memory import SessionMemory, memory
from app.agents.orchestrator import OUT_OF_SCOPE_REPLY, handle_message
from app.agents.order_agent import ORDER_AGENT_SPEC
from app.agents.router_agent import route_message
from app.agents.runner import UNAVAILABLE_FALLBACK_REPLY, run_agent
from app.agents.tools.base import ToolContext
from app.models.menu_item import MenuItem

pytestmark = pytest.mark.agents


def test_agent_only_receives_allowed_tool_specs(db: Session, stub_llm):
    """Verify runner only passes tools from the agent's allowlist to the LLM."""
    ctx = ToolContext(db=db, agent_name="BillingSpecialist")
    stub_llm.set_available(True)
    stub_llm.queue_text("Your bill is ready.")

    run_agent(ctx=ctx, spec=BILLING_AGENT_SPEC, history=[], user_message="Show my bill", client=stub_llm)

    assert len(stub_llm.recorded_calls) >= 1
    call = stub_llm.recorded_calls[0]
    passed_tools = call.get("tools") or []
    passed_names = {t["function"]["name"] for t in passed_tools}

    # Billing agent must only receive its allowed tools
    assert passed_names == set(BILLING_AGENT_SPEC.allowed_tools)
    assert "cancel_order" not in passed_names
    assert "create_order" not in passed_names


def test_tool_call_outside_allowlist_is_blocked(db: Session, stub_llm):
    """Verify tool call outside agent allowlist produces a blocked trace step."""
    ctx = ToolContext(db=db, agent_name="BillingSpecialist")
    stub_llm.set_available(True)

    # Billing agent tries to invoke create_order (which is not in its allowlist)
    stub_llm.queue_tool_call("create_order", {"customer_name": "Infiltrator", "table_no": 1, "items": [{"menu_item_id": 1, "quantity": 1}]})
    stub_llm.queue_text("Sorry, I cannot place orders.")

    result = run_agent(ctx=ctx, spec=BILLING_AGENT_SPEC, history=[], user_message="Create an order", client=stub_llm)

    # Must contain a blocked step
    blocked_steps = [s for s in result.trace if s.kind == "blocked"]
    assert len(blocked_steps) == 1
    assert "not permitted" in blocked_steps[0].summary.lower()


def test_malformed_tool_call_json_becomes_invalid_arguments(db: Session, stub_llm):
    """Verify corrupted JSON tool arguments result in invalid_arguments result without crashing."""
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    stub_llm.set_available(True)

    # Provide raw non-JSON text in arguments
    tc = ToolCallRaw(id="call_corrupt", name="get_menu", arguments="NOT_JSON{{{")
    stub_llm.queue_response(ChatCompletionResult(content=None, tool_calls=[tc]))
    stub_llm.queue_text("I could not load the menu.")

    result = run_agent(ctx=ctx, spec=ORDER_AGENT_SPEC, history=[], user_message="Show menu", client=stub_llm)
    assert result.reply == "I could not load the menu."


def test_runner_stops_at_max_steps(db: Session, stub_llm, settings_override):
    """Verify looping agent stops at AGENT_MAX_STEPS with stopped_reason='max_steps'."""
    settings_override(AGENT_MAX_STEPS=3)
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    stub_llm.set_available(True)

    # Loop tool calls
    for _ in range(5):
        stub_llm.queue_tool_call("get_menu", {})

    result = run_agent(ctx=ctx, spec=ORDER_AGENT_SPEC, history=[], user_message="Loop please", client=stub_llm)
    assert result.stopped_reason == "max_steps"
    assert result.steps_used == 3


def test_runner_stops_at_max_tool_calls(db: Session, stub_llm, settings_override):
    """Verify agent stops when cumulative tool call cap is reached."""
    settings_override(AGENT_MAX_TOOL_CALLS=2)
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    stub_llm.set_available(True)

    # Queue 3 tool calls in a single step
    stub_llm.queue_tool_calls([("get_menu", {}), ("get_menu", {}), ("get_menu", {})])
    stub_llm.queue_text("Done.")

    result = run_agent(ctx=ctx, spec=ORDER_AGENT_SPEC, history=[], user_message="Fetch all", client=stub_llm)
    assert result.stopped_reason in ("max_tool_calls", "max_steps")


def test_runner_timeout(db: Session, stub_llm, monkeypatch, settings_override):
    """Verify timeout expiration results in stopped_reason='timeout'."""
    settings_override(AGENT_TIMEOUT_SECONDS=1.0)
    ctx = ToolContext(db=db, agent_name="OrderSpecialist")
    stub_llm.set_available(True)

    # Fake wall-clock progression
    start_time = 100.0
    times = [start_time, start_time + 0.5, start_time + 10.0]

    def _mock_time():
        return times.pop(0) if times else 200.0

    monkeypatch.setattr("time.time", _mock_time)
    stub_llm.queue_tool_call("get_menu", {})

    result = run_agent(ctx=ctx, spec=ORDER_AGENT_SPEC, history=[], user_message="Show menu", client=stub_llm)
    assert result.stopped_reason == "timeout"


def test_router_out_of_scope_makes_no_specialist_call(db: Session, stub_llm):
    """Verify out-of-scope query answers immediately without invoking specialist agent."""
    stub_llm.set_available(True)
    # Router returns out_of_scope
    stub_llm.queue_text('{"target": "out_of_scope", "reason": "Weather question"}')

    res = handle_message(db=db, session_id="test_sess", message="What is the weather today?", client=stub_llm)
    assert res.agent == "router_agent"
    assert res.reply == OUT_OF_SCOPE_REPLY
    assert res.tool_calls_used == 0


def test_router_keyword_fallback_on_corrupt_json(db: Session, stub_llm):
    """Verify keyword router catches orders if LLM router emits corrupt JSON."""
    stub_llm.set_available(True)
    # LLM router emits corrupt non-JSON
    stub_llm.queue_text("I AM THINKING: ROUTE THIS TO ORDER")
    # Specialist agent reply
    stub_llm.queue_text("Here is our menu.")

    res = handle_message(db=db, session_id="test_sess", message="Show me the food menu", client=stub_llm)
    assert res.agent == "order_agent"


def test_llm_off_gives_fixed_unavailable_reply(db: Session, stub_llm):
    """Verify fallback reply when LLM is unavailable."""
    stub_llm.set_available(False)
    res = handle_message(db=db, session_id="test_sess", message="Hello", client=stub_llm)
    assert res.source == "fallback"
    assert res.reply == UNAVAILABLE_FALLBACK_REPLY


def test_session_memory_capping():
    """Verify session memory caps history turns and concurrent sessions."""
    mem = SessionMemory(max_sessions=2)

    # Add 10 turns to session 1
    for i in range(10):
        mem.add_turn("s1", f"user {i}", f"assistant {i}")

    h1 = mem.get_history("s1")
    # Default is max 6 turns (12 messages)
    assert len(h1) <= 12

    # Add session 2 and session 3 -> session 1 should be evicted (max_sessions=2)
    mem.add_turn("s2", "hi", "hello")
    mem.add_turn("s3", "hi", "hello")

    assert mem.get_history("s1") == []
    assert len(mem.get_history("s2")) == 2
    assert len(mem.get_history("s3")) == 2
