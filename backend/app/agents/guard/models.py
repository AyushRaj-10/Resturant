"""Data models and context definitions for the deterministic guardrail layer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Literal, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field

GuardOutcome = Literal["allow", "block", "needs_confirmation"]


class GuardDecision(BaseModel):
    """Result of policy evaluation for a proposed tool execution."""

    model_config = ConfigDict(extra="forbid")

    outcome: GuardOutcome = Field(..., description="Action determination: allow, block, or needs_confirmation")
    code: str = Field(..., description="Short machine-readable decision code")
    reason: str = Field(..., description="Human-readable explanation of the policy decision")


@dataclass
class GuardContext:
    """Contextual metadata evaluated by guard policies."""

    agent_name: str
    allowed_tools: FrozenSet[str]
    session_id: str
    request_id: str
    user_messages: List[str] = field(default_factory=list)
    writes_used: int = 0
    destructive_used: int = 0
    seen_calls: Set[Tuple[str, str]] = field(default_factory=set)


ActionStatus = Literal["pending", "approved", "rejected", "expired", "consumed"]


@dataclass
class PendingAction:
    """A proposed destructive tool action held in memory awaiting human confirmation."""

    confirmation_id: str
    session_id: str
    agent_name: str
    tool_name: str
    arguments: Dict[str, Any]
    summary: str
    snapshot: Dict[str, Any]
    created_at: datetime
    expires_at: datetime
    status: ActionStatus = "pending"
