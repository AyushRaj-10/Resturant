"""Base models and specs for the multi-agent execution layer."""

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class AgentSpec:
    """Specification defining an agent's persona, instructions, and tool permissions."""

    name: str
    description: str
    system_prompt: str
    allowed_tools: FrozenSet[str]


TraceStepKind = Literal["tool_call", "tool_result", "message", "blocked"]


class TraceStep(BaseModel):
    """A single diagnostic step in an agent run trace."""

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(..., description="Name of the agent generating this trace step")
    kind: TraceStepKind = Field(..., description="Category of event in the execution trace")
    tool: Optional[str] = Field(default=None, description="Name of the tool invoked, if any")
    arguments: Optional[Dict[str, Any]] = Field(default=None, description="Tool invocation arguments, if any")
    ok: Optional[bool] = Field(default=None, description="Tool execution outcome, if applicable")
    summary: str = Field(..., description="Human-readable summary of the action or outcome")


StoppedReason = Literal[
    "completed",
    "max_steps",
    "max_tool_calls",
    "timeout",
    "llm_unavailable",
    "error",
]


from datetime import datetime


class PendingConfirmationInfo(BaseModel):
    """Details of an action awaiting human approval."""

    model_config = ConfigDict(extra="forbid")

    confirmation_id: str = Field(..., description="Unique unguessable confirmation token")
    summary: str = Field(..., description="Human-readable description of proposed action")
    expires_at: Any = Field(..., description="ISO timestamp when action confirmation expires")


class AgentRunResult(BaseModel):
    """Comprehensive return container for an agent or orchestrator run."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(..., description="Final textual reply to present to the user")
    agent: str = Field(..., description="Name of the agent that produced the final reply")
    trace: List[TraceStep] = Field(default_factory=list, description="Ordered execution trace of actions taken")
    source: Literal["llm", "fallback"] = Field(..., description="Origin of the response")
    steps_used: int = Field(default=0, description="Number of LLM round-trips performed")
    tool_calls_used: int = Field(default=0, description="Total number of tool calls executed")
    stopped_reason: StoppedReason = Field(..., description="Reason the agent loop concluded")
    pending_confirmation: Optional[PendingConfirmationInfo] = Field(
        default=None,
        description="Pending action metadata if confirmation is required",
    )
