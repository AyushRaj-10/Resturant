"""Tool registry, discovery, Groq-compatible LLM schema export, and execution pipeline."""

import copy
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ValidationError
from app.agents.tools.base import RiskLevel, ToolContext, ToolError, ToolResult, ToolSpec
from app.agents.tools.definitions import TOOL_DEFINITIONS
from app.services.exceptions import ConflictError, NotFoundError, ValidationRuleError

logger = logging.getLogger(__name__)

# Primary lookup mapping of tool name -> ToolSpec
TOOLS: Dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_DEFINITIONS}


def get_tool(name: str) -> Optional[ToolSpec]:
    """Retrieve a ToolSpec by its unique name."""
    return TOOLS.get(name)


def list_tools(
    risk: Optional[RiskLevel] = None,
    names: Optional[Set[str]] = None,
) -> List[ToolSpec]:
    """List registered tools with optional risk and allowlist filters."""
    tools = list(TOOLS.values())
    if risk is not None:
        tools = [t for t in tools if t.risk == risk]
    if names is not None:
        tools = [t for t in tools if t.name in names]
    return tools


def clean_schema_for_llm(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Inline $defs references and enforce additionalProperties=false recursively for LLMs."""
    defs = schema.get("$defs", {})

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                if ref_key in defs:
                    resolved = copy.deepcopy(defs[ref_key])
                    if "description" in node:
                        resolved["description"] = node["description"]
                    return _resolve(resolved)
            cleaned = {}
            for k, v in node.items():
                if k in {"$defs", "title"}:
                    continue
                cleaned[k] = _resolve(v)
            if cleaned.get("type") == "object" or "properties" in cleaned:
                cleaned["additionalProperties"] = False
            return cleaned
        elif isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    cleaned_schema = _resolve(copy.deepcopy(schema))
    if cleaned_schema.get("type") == "object" or "properties" in cleaned_schema:
        cleaned_schema["additionalProperties"] = False
    return cleaned_schema


def to_llm_tool_specs(names: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Export tool definitions in OpenAI/Groq function-calling JSON format."""
    tools = list_tools(names=names)
    specs: List[Dict[str, Any]] = []
    for tool in tools:
        raw_schema = tool.args_model.model_json_schema()
        cleaned_schema = clean_schema_for_llm(raw_schema)
        specs.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": cleaned_schema,
            },
        })
    return specs


# =========================================================================
# Execution Pipeline (Two-Stage Architecture with Step 11 Guard Hook Point)
# =========================================================================

def _prepare_call(
    name: str,
    raw_args: Dict[str, Any],
) -> Tuple[Optional[ToolSpec], Optional[BaseModel], Optional[ToolResult]]:
    """Stage 1: Tool lookup and strict argument validation against args_model."""
    tool = get_tool(name)
    if tool is None:
        return None, None, ToolResult(
            ok=False,
            error=ToolError(
                type="unknown_tool",
                message=f"Unknown tool '{name}'. Available tools: {', '.join(sorted(TOOLS.keys()))}",
            ),
        )

    try:
        validated_args = tool.args_model.model_validate(raw_args if raw_args is not None else {})
        return tool, validated_args, None
    except ValidationError as exc:
        errors_summary = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []))
            msg = err.get("msg", "Invalid value")
            errors_summary.append(f"{loc}: {msg}" if loc else msg)
        readable_msg = f"Invalid arguments for tool '{name}': {'; '.join(errors_summary)}"
        return tool, None, ToolResult(
            ok=False,
            error=ToolError(
                type="invalid_arguments",
                message=readable_msg,
            ),
        )


def _run_call(ctx: ToolContext, tool: ToolSpec, args: BaseModel) -> ToolResult:
    """Stage 2: Handler execution with error mapping and automatic DB rollback on failure."""
    try:
        data = tool.handler(ctx, args)
        return ToolResult(ok=True, data=data, error=None)
    except NotFoundError as exc:
        ctx.db.rollback()
        return ToolResult(
            ok=False,
            error=ToolError(type="not_found", message=str(exc)),
        )
    except ValidationRuleError as exc:
        ctx.db.rollback()
        return ToolResult(
            ok=False,
            error=ToolError(type="validation", message=str(exc)),
        )
    except ConflictError as exc:
        ctx.db.rollback()
        return ToolResult(
            ok=False,
            error=ToolError(type="conflict", message=str(exc)),
        )
    except Exception as exc:
        ctx.db.rollback()
        logger.exception("Unexpected error executing tool '%s': %s", tool.name, exc)
        return ToolResult(
            ok=False,
            error=ToolError(
                type="internal",
                message="An internal error occurred while executing the tool.",
            ),
        )


from app.models.enums import AuditDecision
from app.models.order import Order
from sqlalchemy.orm import Session



def _build_order_snapshot_and_summary(
    db: Session,
    tool_name: str,
    args: Dict[str, Any],
) -> Tuple[Dict[str, Any], str]:
    order_id = args.get("order_id")
    order = db.get(Order, order_id) if order_id is not None else None
    if order is not None:
        snapshot = {
            "order_id": order.id,
            "customer_name": order.customer_name,
            "table_no": order.table_no,
            "status": order.status.value,
            "total_bill": str(order.total_bill),
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        }
        action_verb = "Cancel" if "cancel" in tool_name else ("Delete" if "delete" in tool_name else tool_name.replace("_", " ").title())
        summary = f"{action_verb} Order #{order.id} for {order.customer_name} (Status: {order.status.value}, Total: ₹{order.total_bill})"
    else:
        snapshot = {"order_id": order_id}
        action_verb = tool_name.replace("_", " ").title()
        summary = f"{action_verb} Order #{order_id}"
    return snapshot, summary


def execute_tool(
    ctx: ToolContext,
    name: str,
    raw_args: Dict[str, Any],
    guard_ctx: Optional[Any] = None,
) -> ToolResult:
    """Execute an agent tool with strict arguments, deterministic guard evaluation, and fail-closed audit logging."""
    from app.agents.guard.audit import log_decision
    from app.agents.guard.confirmations import confirmations_store
    from app.agents.guard.guard import evaluate_call
    from app.agents.guard.models import GuardContext

    # -------------------------------------------------------------------------
    # Stage 1: Preparation (lookup + strict argument validation)
    # -------------------------------------------------------------------------
    tool, validated_args, prep_error = _prepare_call(name, raw_args)
    if prep_error is not None:
        risk = tool.risk if tool else RiskLevel.READ
        agent_name = guard_ctx.agent_name if guard_ctx else ctx.agent_name
        req_id = guard_ctx.request_id if guard_ctx else ctx.request_id
        sess_id = guard_ctx.session_id if guard_ctx else ctx.session_id
        try:
            log_decision(
                agent_name=agent_name,
                tool_name=name,
                arguments=raw_args,
                decision=AuditDecision.BLOCKED,
                reason=f"[{prep_error.error.type.upper()}] {prep_error.error.message}",
                result=None,
                session_id=sess_id,
                request_id=req_id,
                risk=risk,
            )
        except Exception:
            pass
        return prep_error

    # =========================================================================
    # Stage 1.5: Guard Evaluation (Deterministic Policy Checks)
    # =========================================================================
    if guard_ctx is None:
        guard_ctx = GuardContext(
            agent_name=ctx.agent_name,
            allowed_tools=frozenset(TOOLS.keys()),
            session_id=ctx.session_id or "default",
            request_id=ctx.request_id,
            user_messages=list(ctx.user_messages),
        )

    guard_decision = evaluate_call(tool, raw_args, guard_ctx, ctx.db)

    # 1. Blocked by policy
    if guard_decision.outcome == "block":
        try:
            log_decision(
                agent_name=guard_ctx.agent_name,
                tool_name=tool.name,
                arguments=raw_args,
                decision=AuditDecision.BLOCKED,
                reason=f"[{guard_decision.code}] {guard_decision.reason}",
                result=None,
                session_id=guard_ctx.session_id,
                request_id=guard_ctx.request_id,
                risk=tool.risk,
            )
        except Exception:
            if tool.risk in {RiskLevel.WRITE, RiskLevel.DESTRUCTIVE}:
                return ToolResult(
                    ok=False,
                    error=ToolError(type="blocked", message="Operation blocked: audit logging failed (fail-closed policy)."),
                )
        return ToolResult(
            ok=False,
            error=ToolError(type="blocked", message=guard_decision.reason),
        )

    # 2. Needs Human Confirmation
    if guard_decision.outcome == "needs_confirmation":
        snapshot, summary = _build_order_snapshot_and_summary(ctx.db, tool.name, raw_args)
        pending_act = confirmations_store.create_pending_action(
            session_id=guard_ctx.session_id,
            agent_name=guard_ctx.agent_name,
            tool_name=tool.name,
            arguments=raw_args,
            summary=summary,
            snapshot=snapshot,
        )
        guard_ctx.destructive_used += 1

        try:
            log_decision(
                agent_name=guard_ctx.agent_name,
                tool_name=tool.name,
                arguments=raw_args,
                decision=AuditDecision.PENDING_CONFIRMATION,
                reason=f"[{guard_decision.code}] {guard_decision.reason}",
                result={"confirmation_id": pending_act.confirmation_id, "summary": summary},
                session_id=guard_ctx.session_id,
                request_id=guard_ctx.request_id,
                risk=tool.risk,
            )
        except Exception:
            confirmations_store.update_status(pending_act.confirmation_id, "rejected")
            return ToolResult(
                ok=False,
                error=ToolError(type="blocked", message="Operation blocked: audit logging failed (fail-closed policy)."),
            )

        return ToolResult(
            ok=False,
            error=ToolError(
                type="pending_confirmation",
                message="This action needs the user's confirmation. It has NOT been executed.",
            ),
            confirmation_id=pending_act.confirmation_id,
        )

    # 3. Allowed
    if tool.risk == RiskLevel.WRITE:
        guard_ctx.writes_used += 1

    # Pre-execution fail-closed audit check for state-modifying actions
    if tool.risk in {RiskLevel.WRITE, RiskLevel.DESTRUCTIVE}:
        try:
            log_decision(
                agent_name=guard_ctx.agent_name,
                tool_name=tool.name,
                arguments=raw_args,
                decision=AuditDecision.ALLOWED,
                reason=f"[{guard_decision.code}] {guard_decision.reason}",
                result={"status": "executing"},
                session_id=guard_ctx.session_id,
                request_id=guard_ctx.request_id,
                risk=tool.risk,
            )
        except Exception:
            return ToolResult(
                ok=False,
                error=ToolError(
                    type="blocked",
                    message="Operation blocked: audit logging failed (fail-closed policy).",
                ),
            )

    # -------------------------------------------------------------------------
    # Stage 2: Execution (handler dispatch + domain error mapping)
    # -------------------------------------------------------------------------
    result = _run_call(ctx, tool, validated_args)

    audit_reason = f"[{guard_decision.code}] {guard_decision.reason}"
    if not result.ok:
        audit_reason += f" | Handler failed: {result.error.message if result.error else 'unknown'}"

    try:
        log_decision(
            agent_name=guard_ctx.agent_name,
            tool_name=tool.name,
            arguments=raw_args,
            decision=AuditDecision.ALLOWED,
            reason=audit_reason,
            result=result.data if result.ok else {"error": result.error.model_dump() if result.error else None},
            session_id=guard_ctx.session_id,
            request_id=guard_ctx.request_id,
            risk=tool.risk,
        )
    except Exception:
        # Fail-closed: rollback if audit logging fails for WRITE/DESTRUCTIVE
        if tool.risk in {RiskLevel.WRITE, RiskLevel.DESTRUCTIVE}:
            ctx.db.rollback()
            return ToolResult(
                ok=False,
                error=ToolError(
                    type="blocked",
                    message="Operation blocked: audit logging failed (fail-closed policy).",
                ),
            )

    return result
