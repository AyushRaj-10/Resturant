"""Deterministic policy evaluator enforcing safety checks in sequential order."""

import logging
from typing import Any, Dict
from sqlalchemy.orm import Session
from app.agents.guard.models import GuardContext, GuardDecision
from app.agents.guard.policy import (
    check_allowlist,
    check_business_rules,
    check_confirmation_requirement,
    check_duplicate_calls,
    check_kill_switches,
    check_provenance,
    check_request_caps,
    check_session_rate_limit,
    check_value_limits,
)
from app.agents.tools.base import ToolSpec
from app.config import get_settings

logger = logging.getLogger(__name__)


def evaluate_call(
    tool_spec: ToolSpec,
    raw_args: Dict[str, Any],
    guard_ctx: GuardContext,
    db: Session,
) -> GuardDecision:
    """Evaluate a proposed tool call through the 9 deterministic guard rules in strict order.

    Returns the first failing GuardDecision, or the final confirmation/allow decision.
    """
    settings = get_settings()

    # Rule 1: Kill Switches
    decision = check_kill_switches(tool_spec, settings)
    if decision:
        return decision

    # Rule 2: Agent Allowlist
    decision = check_allowlist(tool_spec.name, guard_ctx)
    if decision:
        return decision

    # Rule 3: Session Rate Limit
    max_rate = int(getattr(settings, "AGENT_MAX_TOOL_CALLS_PER_MINUTE_PER_SESSION", 20))
    decision = check_session_rate_limit(guard_ctx.session_id, max_rate)
    if decision:
        return decision

    # Rule 4: Per-Request Action Caps
    decision = check_request_caps(tool_spec, guard_ctx, settings)
    if decision:
        return decision

    # Rule 5: Duplicate Calls Prevention
    decision = check_duplicate_calls(tool_spec.name, raw_args, guard_ctx)
    if decision:
        return decision

    # Rule 6: Provenance Check (Human Token Presence)
    decision = check_provenance(tool_spec, raw_args, guard_ctx.user_messages)
    if decision:
        return decision

    # Rule 7: Business Rules Pre-check
    decision = check_business_rules(tool_spec.name, raw_args, db)
    if decision:
        return decision

    # Rule 8: Value Limits
    decision = check_value_limits(tool_spec.name, raw_args, db, settings)
    if decision:
        return decision

    # Rule 9: Confirmation Requirement
    return check_confirmation_requirement(tool_spec, raw_args)
