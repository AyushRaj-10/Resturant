"""Order specialist agent definition and specification."""

from app.agents.base import AgentSpec
from app.agents.prompts import ORDER_AGENT_SYSTEM_PROMPT

ORDER_AGENT_ALLOWED_TOOLS = frozenset({
    "get_menu",
    "list_orders",
    "get_order",
    "get_allowed_actions",
    "create_order",
    "update_quantity",
    "cancel_order",
    "delete_order",
})

ORDER_AGENT_SPEC = AgentSpec(
    name="order_agent",
    description="Specialist in food menu items, order lookups, placing orders, and modifying item quantities.",
    system_prompt=ORDER_AGENT_SYSTEM_PROMPT,
    allowed_tools=ORDER_AGENT_ALLOWED_TOOLS,
)
