"""Pure deterministic guardrail policy rules for validating agent tool invocations."""

from decimal import Decimal
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.agents.guard.models import GuardContext, GuardDecision
from app.agents.tools.base import RiskLevel, ToolSpec
from app.config import Settings
from app.models.menu_item import MenuItem
from app.models.order import Order
from app.services.order_rules import (
    Operation,
    can_cancel,
    can_delete,
    can_update_bill,
    can_update_quantity,
    explain_block,
)

logger = logging.getLogger(__name__)

# Sliding window session tool-call rate limiter
_session_call_history: Dict[str, List[float]] = {}
_session_history_lock = threading.Lock()


def reset_guard_rate_limits() -> None:
    """Clear in-memory session rate limit history (diagnostic/test helper)."""
    with _session_history_lock:
        _session_call_history.clear()


# =========================================================================
# Rule 1: Kill Switches
# =========================================================================

def check_kill_switches(tool_spec: ToolSpec, settings: Settings) -> Optional[GuardDecision]:
    if tool_spec.risk == RiskLevel.WRITE and not settings.AGENT_WRITES_ENABLED:
        return GuardDecision(
            outcome="block",
            code="WRITES_DISABLED",
            reason="Write operations are temporarily disabled by the system administrator.",
        )
    if tool_spec.risk == RiskLevel.DESTRUCTIVE and not settings.AGENT_DESTRUCTIVE_ENABLED:
        return GuardDecision(
            outcome="block",
            code="DESTRUCTIVE_DISABLED",
            reason="Destructive operations are temporarily disabled by the system administrator.",
        )
    return None


# =========================================================================
# Rule 2: Agent Tool Allowlist
# =========================================================================

def check_allowlist(tool_name: str, guard_ctx: GuardContext) -> Optional[GuardDecision]:
    if tool_name not in guard_ctx.allowed_tools:
        return GuardDecision(
            outcome="block",
            code="NOT_IN_ALLOWLIST",
            reason=f"Tool '{tool_name}' is not permitted for agent '{guard_ctx.agent_name}'.",
        )
    return None


# =========================================================================
# Rule 3: Session Rate Limit (Sliding Window)
# =========================================================================

def check_session_rate_limit(session_id: str, max_per_min: int) -> Optional[GuardDecision]:
    now = time.time()
    cutoff = now - 60.0
    with _session_history_lock:
        timestamps = [t for t in _session_call_history.get(session_id, []) if t > cutoff]
        if len(timestamps) >= max_per_min:
            return GuardDecision(
                outcome="block",
                code="RATE_LIMIT_EXCEEDED",
                reason=f"Session rate limit exceeded: maximum {max_per_min} tool calls per minute.",
            )
        timestamps.append(now)
        _session_call_history[session_id] = timestamps
    return None


# =========================================================================
# Rule 4: Per-Request Action Caps
# =========================================================================

def check_request_caps(tool_spec: ToolSpec, guard_ctx: GuardContext, settings: Settings) -> Optional[GuardDecision]:
    if tool_spec.risk == RiskLevel.WRITE:
        if guard_ctx.writes_used >= settings.AGENT_MAX_WRITES_PER_REQUEST:
            return GuardDecision(
                outcome="block",
                code="MAX_WRITES_EXCEEDED",
                reason=(
                    "Bulk actions are not allowed. You have reached the maximum allowed write operations "
                    "for this request. Please ask for one order at a time."
                ),
            )
    elif tool_spec.risk == RiskLevel.DESTRUCTIVE:
        if guard_ctx.destructive_used >= settings.AGENT_MAX_DESTRUCTIVE_PER_REQUEST:
            return GuardDecision(
                outcome="block",
                code="MAX_DESTRUCTIVE_EXCEEDED",
                reason=(
                    "Bulk destructive actions are not allowed. Only one destructive operation can be "
                    "proposed per request. Please ask for one order at a time."
                ),
            )
    return None


# =========================================================================
# Rule 5: Duplicate Calls Prevention
# =========================================================================

def check_duplicate_calls(tool_name: str, raw_args: Dict[str, Any], guard_ctx: GuardContext) -> Optional[GuardDecision]:
    serialized_args = json.dumps(raw_args, sort_keys=True)
    call_sig = (tool_name, serialized_args)
    if call_sig in guard_ctx.seen_calls:
        return GuardDecision(
            outcome="block",
            code="DUPLICATE_CALL",
            reason=f"Duplicate call to '{tool_name}' with identical arguments was blocked to prevent loops.",
        )
    guard_ctx.seen_calls.add(call_sig)
    return None


# =========================================================================
# Rule 6: Provenance Check (Human Token Presence)
# =========================================================================

def check_provenance(tool_spec: ToolSpec, raw_args: Dict[str, Any], user_messages: List[str]) -> Optional[GuardDecision]:
    """Ensure order_id in sensitive/destructive calls was explicitly written by the human user."""
    if tool_spec.risk == RiskLevel.DESTRUCTIVE or tool_spec.name == "update_bill":
        order_id = raw_args.get("order_id")
        if order_id is not None:
            # Whole token match: \b<order_id>\b
            pattern = re.compile(rf"\b{re.escape(str(order_id))}\b")
            found = any(pattern.search(msg) for msg in user_messages)
            if not found:
                return GuardDecision(
                    outcome="block",
                    code="PROVENANCE_FAILED",
                    reason=(
                        f"Order #{order_id} was not explicitly mentioned in your message. "
                        f"For security, destructive actions and bill modifications must specify the order ID directly."
                    ),
                )
    return None


# =========================================================================
# Rule 7: Business Rules Pre-check (order_rules.py)
# =========================================================================

def check_business_rules(tool_name: str, raw_args: Dict[str, Any], db: Session) -> Optional[GuardDecision]:
    """Inspect current DB state and evaluate pure business rules before any proposal or execution."""
    if tool_name in {"update_quantity", "update_bill", "cancel_order", "delete_order"}:
        order_id = raw_args.get("order_id")
        if order_id is None:
            return None

        order = db.get(Order, order_id)
        if order is None:
            return GuardDecision(
                outcome="block",
                code="ORDER_NOT_FOUND",
                reason=f"Order with ID {order_id} not found.",
            )

        if tool_name == "update_quantity":
            if not can_update_quantity(order.status):
                return GuardDecision(
                    outcome="block",
                    code="BUSINESS_RULE_VIOLATION",
                    reason=explain_block(Operation.UPDATE_QUANTITY, order.status, order_id=order.id),
                )
        elif tool_name == "update_bill":
            if not can_update_bill(order.status):
                return GuardDecision(
                    outcome="block",
                    code="BUSINESS_RULE_VIOLATION",
                    reason=explain_block(Operation.UPDATE_BILL, order.status, order_id=order.id),
                )
        elif tool_name == "cancel_order":
            if not can_cancel(order.status):
                return GuardDecision(
                    outcome="block",
                    code="BUSINESS_RULE_VIOLATION",
                    reason=explain_block(Operation.CANCEL, order.status, order_id=order.id),
                )
        elif tool_name == "delete_order":
            if not can_delete(order.status):
                return GuardDecision(
                    outcome="block",
                    code="BUSINESS_RULE_VIOLATION",
                    reason=explain_block(Operation.DELETE, order.status, order_id=order.id),
                )

    return None


# =========================================================================
# Rule 8: Value Limits
# =========================================================================

def check_value_limits(
    tool_name: str,
    raw_args: Dict[str, Any],
    db: Session,
    settings: Settings,
) -> Optional[GuardDecision]:
    if tool_name == "update_bill":
        discount = raw_args.get("discount_percent")
        if discount is not None:
            try:
                discount_val = float(discount)
                if discount_val > float(settings.AGENT_MAX_DISCOUNT_PERCENT):
                    return GuardDecision(
                        outcome="block",
                        code="DISCOUNT_LIMIT_EXCEEDED",
                        reason=(
                            f"Discount of {discount_val:.1f}% exceeds maximum allowed agent discount of "
                            f"{float(settings.AGENT_MAX_DISCOUNT_PERCENT):.1f}%. A staff member must apply "
                            f"larger discounts directly in the Orders page."
                        ),
                    )
            except (ValueError, TypeError):
                pass

    elif tool_name == "create_order":
        items = raw_args.get("items", [])
        if isinstance(items, list) and items:
            item_ids = [it.get("menu_item_id") for it in items if isinstance(it, dict) and "menu_item_id" in it]
            if item_ids:
                menu_records = list(db.scalars(select(MenuItem).where(MenuItem.id.in_(item_ids))).all())
                price_map = {m.id: m.price for m in menu_records}
                computed_total = sum(
                    (Decimal(str(it.get("quantity", 1))) * price_map.get(it.get("menu_item_id"), Decimal("0.00"))
                     for it in items if isinstance(it, dict)),
                    start=Decimal("0.00"),
                )
                max_total = Decimal(str(settings.AGENT_MAX_ORDER_TOTAL))
                if computed_total > max_total:
                    return GuardDecision(
                        outcome="block",
                        code="ORDER_TOTAL_EXCEEDED",
                        reason=(
                            f"Computed order total (₹{computed_total:.2f}) exceeds the maximum allowed order "
                            f"limit of ₹{max_total:.2f}."
                        ),
                    )
    return None


# =========================================================================
# Rule 9: Confirmation Requirement
# =========================================================================

def check_confirmation_requirement(tool_spec: ToolSpec, raw_args: Dict[str, Any]) -> GuardDecision:
    if tool_spec.risk == RiskLevel.DESTRUCTIVE:
        order_id = raw_args.get("order_id", "specified")
        action_name = tool_spec.name.replace("_", " ")
        return GuardDecision(
            outcome="needs_confirmation",
            code="NEEDS_CONFIRMATION",
            reason=f"This destructive action will {action_name} Order #{order_id}. Human confirmation is required before changes can be made.",
        )
    return GuardDecision(
        outcome="allow",
        code="ALLOW",
        reason=f"Action '{tool_spec.name}' approved by policy.",
    )
