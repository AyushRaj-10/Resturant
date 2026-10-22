"""Agents package for multi-agent workflows and guarded tool definitions."""

from app.agents.base import AgentRunResult, AgentSpec, StoppedReason, TraceStep
from app.agents.billing_agent import BILLING_AGENT_ALLOWED_TOOLS, BILLING_AGENT_SPEC
from app.agents.groq_tools_client import ChatCompletionResult, GroqToolsClient, ToolCallRaw, get_groq_tools_client
from app.agents.memory import SessionMemory, memory
from app.agents.order_agent import ORDER_AGENT_ALLOWED_TOOLS, ORDER_AGENT_SPEC
from app.agents.orchestrator import handle_message
from app.agents.router_agent import RouteDecision, route_message
from app.agents.runner import run_agent
from app.agents.tools import (
    RiskLevel,
    ToolContext,
    ToolError,
    ToolResult,
    ToolSpec,
    execute_tool,
    get_tool,
    list_tools,
    to_llm_tool_specs,
)

__all__ = [
    # Base
    "AgentSpec",
    "AgentRunResult",
    "TraceStep",
    "StoppedReason",
    # Tools
    "RiskLevel",
    "ToolContext",
    "ToolError",
    "ToolResult",
    "ToolSpec",
    "execute_tool",
    "get_tool",
    "list_tools",
    "to_llm_tool_specs",
    # Agents
    "ORDER_AGENT_SPEC",
    "ORDER_AGENT_ALLOWED_TOOLS",
    "BILLING_AGENT_SPEC",
    "BILLING_AGENT_ALLOWED_TOOLS",
    "RouteDecision",
    "route_message",
    # Execution & Memory
    "handle_message",
    "run_agent",
    "SessionMemory",
    "memory",
    "GroqToolsClient",
    "get_groq_tools_client",
    "ChatCompletionResult",
    "ToolCallRaw",
]
