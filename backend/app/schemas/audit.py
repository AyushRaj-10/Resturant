"""Pydantic schemas for agent audit logging."""

from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field
from app.models.enums import AuditDecision


class AgentAuditLogOut(BaseModel):
    """Output representation of an audited agent tool execution."""

    id: int = Field(..., description="Unique database ID of the audit entry")
    agent_name: str = Field(..., description="Name of the executing agent")
    tool_name: str = Field(..., description="Name of the tool invoked by the agent")
    arguments: Optional[Any] = Field(
        default=None,
        description="Arguments passed to the tool invocation",
    )
    decision: AuditDecision = Field(
        ...,
        description="Security rule decision evaluating tool execution",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Justification or rule reason for the decision",
    )
    result: Optional[Any] = Field(
        default=None,
        description="Result payload returned by tool execution if permitted",
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when tool was invoked and audited",
    )

    model_config = ConfigDict(from_attributes=True)
