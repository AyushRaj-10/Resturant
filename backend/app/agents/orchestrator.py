"""Multi-agent orchestrator coordinating intent routing, execution, and memory."""

import logging
from typing import Optional
import uuid
from sqlalchemy.orm import Session
from app.agents.base import AgentRunResult, TraceStep
from app.agents.billing_agent import BILLING_AGENT_SPEC
from app.agents.groq_tools_client import GroqToolsClient, get_groq_tools_client
from app.agents.memory import memory
from app.agents.order_agent import ORDER_AGENT_SPEC
from app.agents.router_agent import route_message
from app.agents.runner import run_agent
from app.agents.tools.base import ToolContext

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_REPLY = (
    "I am the restaurant assistant. I can only assist with food menu inquiries, "
    "placing or looking up orders, and explaining or adjusting bills. "
    "How can I help you with your order today?"
)


def handle_message(
    db: Session,
    session_id: str,
    message: str,
    client: Optional[GroqToolsClient] = None,
) -> AgentRunResult:
    """Orchestrate routing, single-specialist execution, and session memory updates."""
    llm_client = client or get_groq_tools_client()

    # Retrieve existing session history
    history = memory.get_history(session_id)

    # 1. Intent routing
    route_decision = route_message(message, client=llm_client)

    routing_trace_step = TraceStep(
        agent="router_agent",
        kind="message",
        summary=f"Routed to '{route_decision.target}': {route_decision.reason}",
    )

    # 2. Handle out-of-scope intent immediately with no further LLM calls
    if route_decision.target == "out_of_scope":
        reply = OUT_OF_SCOPE_REPLY
        memory.add_turn(session_id, message, reply)
        return AgentRunResult(
            reply=reply,
            agent="router_agent",
            trace=[routing_trace_step],
            source="llm" if llm_client.is_available() else "fallback",
            steps_used=1,
            tool_calls_used=0,
            stopped_reason="completed",
        )

    # 3. Select specialist agent
    if route_decision.target == "billing":
        spec = BILLING_AGENT_SPEC
    else:
        spec = ORDER_AGENT_SPEC

    # 4. Construct tool context with real human messages for provenance verification
    user_messages = [
        turn["content"]
        for turn in history
        if turn.get("role") == "user" and turn.get("content")
    ]
    user_messages.append(message)

    ctx = ToolContext(
        db=db,
        agent_name=spec.name,
        request_id=str(uuid.uuid4()),
        session_id=session_id,
        user_messages=user_messages,
    )

    # 5. Execute specialist agent loop
    result = run_agent(
        ctx=ctx,
        spec=spec,
        history=history,
        user_message=message,
        client=llm_client,
    )

    # Prepend routing decision to trace
    result.trace = [routing_trace_step] + result.trace

    # 6. Save turn to session memory
    memory.add_turn(session_id, message, result.reply)

    return result
