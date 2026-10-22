"""Fail-closed audit logging layer persisting tool evaluation outcomes."""

from datetime import datetime
from decimal import Decimal
import logging
from typing import Any, Dict, Optional
from app.agents.tools.base import RiskLevel
from app.database import SessionLocal
from app.models.audit import AgentAuditLog
from app.models.enums import AuditDecision

logger = logging.getLogger(__name__)

MAX_STRING_LENGTH = 200
MAX_REASON_LENGTH = 255


def _sanitize_for_audit(val: Any) -> Any:
    """Recursively truncate long strings and serialize non-JSON types for safe audit storage."""
    if isinstance(val, dict):
        return {k: _sanitize_for_audit(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_sanitize_for_audit(item) for item in val]
    elif isinstance(val, str):
        if len(val) > MAX_STRING_LENGTH:
            return val[:MAX_STRING_LENGTH] + "... [truncated]"
        return val
    elif isinstance(val, Decimal):
        return str(val)
    elif isinstance(val, datetime):
        return val.isoformat()
    return val


def log_decision(
    agent_name: str,
    tool_name: str,
    arguments: Optional[Dict[str, Any]],
    decision: AuditDecision,
    reason: str,
    result: Optional[Any] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
    risk: RiskLevel = RiskLevel.READ,
) -> None:
    """Persist an audit log entry in its own short-lived session with fail-closed semantics."""
    clean_args = _sanitize_for_audit(arguments or {})
    clean_result = _sanitize_for_audit(result) if result is not None else None

    # Inject metadata into arguments JSON
    if isinstance(clean_args, dict):
        clean_args["_meta"] = {
            "session_id": session_id or "",
            "request_id": request_id or "",
        }

    clean_reason = (reason or "")[:MAX_REASON_LENGTH]

    db = SessionLocal()
    try:
        audit_entry = AgentAuditLog(
            agent_name=agent_name,
            tool_name=tool_name,
            arguments=clean_args,
            decision=decision,
            reason=clean_reason,
            result=clean_result,
        )
        db.add(audit_entry)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed to write audit log for %s (%s): %s", tool_name, decision.value, exc)

        # Fail closed: WRITE and DESTRUCTIVE actions MUST abort if audit log cannot be saved
        if risk in {RiskLevel.WRITE, RiskLevel.DESTRUCTIVE}:
            raise RuntimeError(f"Audit log failure on critical tool '{tool_name}': {exc}") from exc
    finally:
        db.close()
