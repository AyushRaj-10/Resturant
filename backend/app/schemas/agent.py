"""Pydantic schemas for the agent chat, confirmation, and pending action APIs."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.agents.base import PendingConfirmationInfo, StoppedReason, TraceStep


class AgentChatRequest(BaseModel):
    """Request payload for multi-agent assistant chat endpoint."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="User message or query for the restaurant assistant (1-500 characters).",
        examples=["Can I get an order of paneer tikka and 2 butter naan for table 3?"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional conversation session ID. If omitted, a new UUID session is generated.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )


class AgentChatResponse(BaseModel):
    """Response payload returned by the multi-agent assistant."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Active session ID for continuing conversation")
    reply: str = Field(..., description="Assistant textual reply")
    agent: str = Field(..., description="Specialist agent that handled the request")
    trace: List[TraceStep] = Field(default_factory=list, description="Ordered trace of diagnostic steps taken")
    source: Literal["llm", "fallback"] = Field(..., description="Source of response: llm or fallback")
    stopped_reason: StoppedReason = Field(..., description="Reason the agent loop concluded")
    pending_confirmation: Optional[PendingConfirmationInfo] = Field(
        default=None,
        description="Metadata for pending destructive action awaiting confirmation, if any",
    )


class AgentConfirmRequest(BaseModel):
    """Request payload for human approval or rejection of a pending destructive action."""

    model_config = ConfigDict(extra="forbid")

    confirmation_id: str = Field(..., description="Unique confirmation token issued by the guard")
    session_id: str = Field(..., description="Session ID bound to this confirmation")
    approve: bool = Field(..., description="True to approve and execute, False to reject")


class AgentConfirmResponse(BaseModel):
    """Response payload after processing a confirmation decision."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether action was approved and successfully executed")
    message: str = Field(..., description="Human-readable status summary")
    result: Optional[Any] = Field(default=None, description="Output payload from tool execution if approved")


class PendingActionOut(BaseModel):
    """Representation of an active action awaiting human confirmation."""

    model_config = ConfigDict(extra="forbid")

    confirmation_id: str
    session_id: str
    agent_name: str
    tool_name: str
    arguments: Dict[str, Any]
    summary: str
    created_at: str
    expires_at: str
    status: str
