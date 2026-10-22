"""Billing specialist agent definition and specification."""

from app.agents.base import AgentSpec
from app.agents.prompts import BILLING_AGENT_SYSTEM_PROMPT

BILLING_AGENT_ALLOWED_TOOLS = frozenset({
    "get_order",
    "list_orders",
    "get_allowed_actions",
    "update_bill",
})

BILLING_AGENT_SPEC = AgentSpec(
    name="billing_agent",
    description="Specialist in explaining bill charges, reviewing totals, and applying discounts or service charges.",
    system_prompt=BILLING_AGENT_SYSTEM_PROMPT,
    allowed_tools=BILLING_AGENT_ALLOWED_TOOLS,
)
