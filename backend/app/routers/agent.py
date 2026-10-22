"""Agent router providing read-only tool discovery, multi-agent chat, human confirmation, and audit log endpoints."""

from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.agents.guard.audit import log_decision
from app.agents.guard.confirmations import confirmations_store
from app.agents.orchestrator import handle_message
from app.agents.tools.base import RiskLevel
from app.agents.tools.registry import clean_schema_for_llm, list_tools
from app.database import get_db
from app.models.audit import AgentAuditLog
from app.models.enums import AuditDecision
from app.models.order import Order
from app.routers.rate_limiter import check_ai_rate_limit
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    AgentConfirmRequest,
    AgentConfirmResponse,
    PendingActionOut,
)
from app.schemas.audit import AgentAuditLogOut
from app.services import order_service
from app.services.order_rules import Operation, can_cancel, can_delete, explain_block

router = APIRouter(prefix="/agent", tags=["Agent"])


class ToolDiscoveryOut(BaseModel):
    """Metadata and argument schema for a registered agent tool."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Unique tool identifier name")
    description: str = Field(..., description="Detailed description of tool capabilities and limits")
    risk: str = Field(..., description="Risk classification: READ, WRITE, or DESTRUCTIVE")
    requires_confirmation: bool = Field(..., description="Whether tool requires explicit confirmation")
    args_schema: Dict[str, Any] = Field(..., description="Cleaned JSON Schema of accepted tool arguments")
    parameters: Dict[str, Any] = Field(..., description="OpenAI/Groq compatible parameters schema")


@router.get(
    "/tools",
    response_model=List[ToolDiscoveryOut],
    summary="List available agent tools and schemas",
    description="Read-only discovery endpoint. Lists registered tools and argument schemas. Tools cannot be executed over HTTP.",
)
def get_agent_tools() -> List[ToolDiscoveryOut]:
    """Return all registered agent tools with their risk classifications and argument schemas."""
    tools = list_tools()
    results: List[ToolDiscoveryOut] = []
    for tool in tools:
        schema = clean_schema_for_llm(tool.args_model.model_json_schema())
        results.append(
            ToolDiscoveryOut(
                name=tool.name,
                description=tool.description,
                risk=tool.risk.value,
                requires_confirmation=tool.requires_confirmation,
                args_schema=schema,
                parameters=schema,
            )
        )
    return results


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    dependencies=[Depends(check_ai_rate_limit)],
    summary="Chat with the restaurant assistant",
    description="Send a message to the restaurant assistant. Routes to order or billing specialists using function-calling tools.",
)
def agent_chat(
    payload: AgentChatRequest,
    db: Session = Depends(get_db),
) -> AgentChatResponse:
    """Process a user conversational turn through the multi-agent system."""
    session_id = payload.session_id.strip() if payload.session_id and payload.session_id.strip() else str(uuid.uuid4())
    result = handle_message(db=db, session_id=session_id, message=payload.message)
    return AgentChatResponse(
        session_id=session_id,
        reply=result.reply,
        agent=result.agent,
        trace=result.trace,
        source=result.source,
        stopped_reason=result.stopped_reason,
        pending_confirmation=result.pending_confirmation,
    )


# =========================================================================
# Human Confirmation Endpoints
#
# NOTE ON SECURITY ARCHITECTURE:
# This confirm endpoint is the ONLY place in the entire system that executes
# a destructive action on behalf of an agent proposal. It executes only a
# specific action that the deterministic guard already approved and proposed.
# It is NOT a general tool-execution endpoint, and the LLM model has NO way
# to invoke or call this endpoint.
# =========================================================================

@router.post(
    "/confirm",
    response_model=AgentConfirmResponse,
    dependencies=[Depends(check_ai_rate_limit)],
    summary="Approve or reject a pending destructive action",
    description="Human confirmation endpoint for proposed destructive actions (e.g. cancel_order, delete_order). Re-validates state before execution.",
)
def confirm_action(
    payload: AgentConfirmRequest,
    db: Session = Depends(get_db),
) -> AgentConfirmResponse:
    """Approve or reject a proposed destructive action with live state re-validation."""
    action = confirmations_store.get_action(payload.confirmation_id)

    # 1. Unknown token
    if action is None:
        log_decision(
            agent_name="system",
            tool_name="confirm_action",
            arguments={"confirmation_id": payload.confirmation_id, "session_id": payload.session_id},
            decision=AuditDecision.BLOCKED,
            reason="[UNKNOWN_CONFIRMATION] Confirmation ID not found or already pruned.",
            session_id=payload.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Confirmation request not found or expired.",
        )

    # 2. Session mismatch
    if action.session_id != payload.session_id:
        log_decision(
            agent_name=action.agent_name,
            tool_name=action.tool_name,
            arguments=action.arguments,
            decision=AuditDecision.BLOCKED,
            reason="[SESSION_MISMATCH] Confirmation token belongs to a different session.",
            session_id=payload.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Confirmation token does not match the active session.",
        )

    # 3. Expired token
    if action.status == "expired":
        log_decision(
            agent_name=action.agent_name,
            tool_name=action.tool_name,
            arguments=action.arguments,
            decision=AuditDecision.BLOCKED,
            reason="[EXPIRED_CONFIRMATION] Confirmation token has expired.",
            session_id=payload.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Confirmation token has expired. Please request the action again.",
        )

    # 4. Already processed (single-use enforcement)
    if action.status in {"consumed", "rejected", "approved"}:
        log_decision(
            agent_name=action.agent_name,
            tool_name=action.tool_name,
            arguments=action.arguments,
            decision=AuditDecision.BLOCKED,
            reason=f"[ALREADY_PROCESSED] Confirmation token has already been {action.status}.",
            session_id=payload.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This confirmation has already been {action.status}.",
        )

    # 5. User Rejection
    if not payload.approve:
        confirmations_store.update_status(payload.confirmation_id, "rejected")
        log_decision(
            agent_name=action.agent_name,
            tool_name=action.tool_name,
            arguments=action.arguments,
            decision=AuditDecision.BLOCKED,
            reason="rejected by user",
            session_id=action.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        return AgentConfirmResponse(
            success=False,
            message="Action rejected by user. No changes were made.",
            result=None,
        )

    # 6. User Approval -> Execution Time Re-validation
    order_id = action.arguments.get("order_id")
    order = db.get(Order, order_id) if order_id is not None else None
    if order is None:
        confirmations_store.update_status(payload.confirmation_id, "rejected")
        log_decision(
            agent_name=action.agent_name,
            tool_name=action.tool_name,
            arguments=action.arguments,
            decision=AuditDecision.BLOCKED,
            reason="[ORDER_NOT_FOUND] Target order no longer exists.",
            session_id=action.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order #{order_id} no longer exists.",
        )

    # Check business rules against live order status
    if action.tool_name == "cancel_order":
        if not can_cancel(order.status):
            reason_msg = explain_block(Operation.CANCEL, order.status, order_id=order.id)
            confirmations_store.update_status(payload.confirmation_id, "rejected")
            log_decision(
                agent_name=action.agent_name,
                tool_name=action.tool_name,
                arguments=action.arguments,
                decision=AuditDecision.BLOCKED,
                reason=f"[STATE_CHANGED] Business rule check failed: {reason_msg}",
                session_id=action.session_id,
                risk=RiskLevel.DESTRUCTIVE,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot cancel order: {reason_msg}",
            )
    elif action.tool_name == "delete_order":
        if not can_delete(order.status):
            reason_msg = explain_block(Operation.DELETE, order.status, order_id=order.id)
            confirmations_store.update_status(payload.confirmation_id, "rejected")
            log_decision(
                agent_name=action.agent_name,
                tool_name=action.tool_name,
                arguments=action.arguments,
                decision=AuditDecision.BLOCKED,
                reason=f"[STATE_CHANGED] Business rule check failed: {reason_msg}",
                session_id=action.session_id,
                risk=RiskLevel.DESTRUCTIVE,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete order: {reason_msg}",
            )

    # Compare snapshot fingerprint (status, total_bill, updated_at)
    snap = action.snapshot or {}
    current_status = order.status.value
    current_total = str(order.total_bill)
    current_updated = order.updated_at.isoformat() if order.updated_at else None

    fingerprint_mismatch = False
    if snap.get("status") != current_status or snap.get("total_bill") != current_total:
        fingerprint_mismatch = True
    if snap.get("updated_at") and current_updated and snap.get("updated_at") != current_updated:
        fingerprint_mismatch = True

    if fingerprint_mismatch:
        confirmations_store.update_status(payload.confirmation_id, "rejected")
        log_decision(
            agent_name=action.agent_name,
            tool_name=action.tool_name,
            arguments=action.arguments,
            decision=AuditDecision.BLOCKED,
            reason="[FINGERPRINT_MISMATCH] Order state changed since confirmation proposal was generated.",
            session_id=action.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The order state has changed since this action was proposed. Please review the order and request the action again.",
        )

    # Execute the verified destructive action
    if action.tool_name == "cancel_order":
        cancelled = order_service.cancel_order(db, order_id=order.id)
        result_payload = {
            "id": cancelled.id,
            "status": cancelled.status.value,
            "customer_name": cancelled.customer_name,
            "total_bill": str(cancelled.total_bill),
        }
        confirmations_store.update_status(payload.confirmation_id, "consumed")
        log_decision(
            agent_name=action.agent_name,
            tool_name=action.tool_name,
            arguments=action.arguments,
            decision=AuditDecision.ALLOWED,
            reason="confirmed by user",
            result=result_payload,
            session_id=action.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        return AgentConfirmResponse(
            success=True,
            message=f"Order #{order.id} has been cancelled.",
            result=result_payload,
        )

    elif action.tool_name == "delete_order":
        order_service.delete_order(db, order_id=order.id)
        result_payload = {
            "deleted": True,
            "order_id": order.id,
            "message": f"Order #{order.id} has been permanently deleted.",
        }
        confirmations_store.update_status(payload.confirmation_id, "consumed")
        log_decision(
            agent_name=action.agent_name,
            tool_name=action.tool_name,
            arguments=action.arguments,
            decision=AuditDecision.ALLOWED,
            reason="confirmed by user",
            result=result_payload,
            session_id=action.session_id,
            risk=RiskLevel.DESTRUCTIVE,
        )
        return AgentConfirmResponse(
            success=True,
            message=f"Order #{order.id} has been permanently deleted.",
            result=result_payload,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported destructive action '{action.tool_name}'.",
    )


@router.get(
    "/pending",
    response_model=List[PendingActionOut],
    summary="List pending actions awaiting confirmation",
    description="Returns live pending destructive actions for a given session that await human confirmation.",
)
def get_pending_actions(session_id: str = Query(..., description="Active session ID")) -> List[PendingActionOut]:
    """Retrieve active pending confirmation actions for the specified session."""
    actions = confirmations_store.list_pending(session_id=session_id)
    return [
        PendingActionOut(
            confirmation_id=act.confirmation_id,
            session_id=act.session_id,
            agent_name=act.agent_name,
            tool_name=act.tool_name,
            arguments=act.arguments,
            summary=act.summary,
            created_at=act.created_at.isoformat(),
            expires_at=act.expires_at.isoformat(),
            status=act.status,
        )
        for act in actions
    ]


@router.get(
    "/audit-log",
    response_model=List[AgentAuditLogOut],
    summary="Retrieve agent audit logs",
    description="Read-only paginated audit log of all tool invocations and security decisions. Logs cannot be modified or deleted.",
)
def get_audit_logs(
    decision: Optional[AuditDecision] = Query(None, description="Filter by decision enum (ALLOWED, BLOCKED, PENDING_CONFIRMATION)"),
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    tool_name: Optional[str] = Query(None, description="Filter by tool name"),
    skip: int = Query(0, ge=0, description="Number of log records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of log records to return"),
    db: Session = Depends(get_db),
) -> List[AgentAuditLogOut]:
    """Retrieve immutable audit logs recorded for agent activity with optional filtering."""
    query = select(AgentAuditLog).order_by(AgentAuditLog.id.desc())
    if decision is not None:
        query = query.where(AgentAuditLog.decision == decision)
    if agent_name is not None:
        query = query.where(AgentAuditLog.agent_name == agent_name)
    if tool_name is not None:
        query = query.where(AgentAuditLog.tool_name == tool_name)

    query = query.offset(skip).limit(limit)
    return list(db.scalars(query).all())
