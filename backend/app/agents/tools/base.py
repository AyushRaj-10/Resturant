"""Base definitions, context, result models, and specifications for agent tools."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Literal, Optional, Type, Union
import uuid

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session


class RiskLevel(str, Enum):
    """Risk classification for tool actions."""

    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


@dataclass
class ToolContext:
    """Execution context passed to every tool invocation.

    In Step 11, agent_name and request_id will be used for audit logging.
    """

    db: Session
    agent_name: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))


ToolErrorType = Literal[
    "not_found",
    "validation",
    "conflict",
    "invalid_arguments",
    "unknown_tool",
    "internal",
]


class ToolError(BaseModel):
    """Standardized error payload returned upon tool execution failure."""

    model_config = ConfigDict(extra="forbid")

    type: ToolErrorType
    message: str


class ToolResult(BaseModel):
    """Uniform return container for all agent tool executions. Never raises exceptions."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: Optional[Union[dict, list]] = None
    error: Optional[ToolError] = None


@dataclass
class ToolSpec:
    """Self-describing specification for an executable agent tool."""

    name: str
    description: str
    args_model: Type[BaseModel]
    risk: RiskLevel
    handler: Callable[[ToolContext, Any], Any]
    requires_confirmation: bool = False

    def __post_init__(self):
        # DESTRUCTIVE actions require human confirmation metadata by default
        if self.risk == RiskLevel.DESTRUCTIVE:
            self.requires_confirmation = True
