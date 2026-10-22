"""Intent classification router agent assigning user queries to specialized agents."""

import json
import logging
import re
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.agents.groq_tools_client import GroqToolsClient, get_groq_tools_client
from app.agents.prompts import ROUTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

RouteTarget = Literal["order", "billing", "out_of_scope"]


class RouteDecision(BaseModel):
    """Pydantic model representing routing destination and justification."""

    model_config = ConfigDict(extra="forbid")

    target: RouteTarget = Field(..., description="Destination specialist or out-of-scope designation")
    reason: str = Field(..., description="Short explanation for the classification")


def _fallback_keyword_route(message: str) -> RouteDecision:
    """Deterministic keyword-based intent classification when LLM is unavailable or fails."""
    lower = message.lower()

    # Common non-restaurant queries
    out_of_scope_cues = ["weather", "forecast", "who is", "president", "code", "python", "capital of"]
    if any(cue in lower for cue in out_of_scope_cues):
        return RouteDecision(
            target="out_of_scope",
            reason="Message appears unrelated to dining orders or billing.",
        )

    billing_keywords = ["bill", "discount", "service charge", "charge", "subtotal", "total"]
    if any(kw in lower for kw in billing_keywords):
        return RouteDecision(
            target="billing",
            reason="Keyword matched billing inquiries.",
        )

    return RouteDecision(
        target="order",
        reason="Defaulted to order specialist for menu and dining requests.",
    )


def _extract_json_block(text: str) -> str:
    """Extract raw JSON substring from potentially markdown-wrapped model output."""
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return match.group(0)
    return text.strip()


def route_message(
    message: str,
    client: Optional[GroqToolsClient] = None,
) -> RouteDecision:
    """Classify the user message into 'order', 'billing', or 'out_of_scope'."""
    llm_client = client or get_groq_tools_client()

    if not llm_client.is_available():
        return _fallback_keyword_route(message)

    messages = [
        {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ]

    try:
        completion = llm_client.chat(messages=messages, tools=None)
        if completion.error or not completion.content:
            logger.warning("Router completion failed: %s; using keyword fallback", completion.error)
            return _fallback_keyword_route(message)

        json_str = _extract_json_block(completion.content)
        parsed = json.loads(json_str)
        return RouteDecision.model_validate(parsed)
    except Exception as exc:
        logger.warning("Router JSON parsing error (%s); using keyword fallback", exc)
        return _fallback_keyword_route(message)
