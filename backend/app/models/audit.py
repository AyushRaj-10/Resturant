from datetime import datetime
from typing import Any, Optional
from sqlalchemy import DateTime, Enum as SQLEnum, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.enums import AuditDecision


class AgentAuditLog(Base):
    """Audit log entry capturing agent tool invocations, decisions, and outcomes."""

    __tablename__ = "agent_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(50), nullable=False)
    arguments: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    decision: Mapped[AuditDecision] = mapped_column(
        SQLEnum(AuditDecision, name="audit_decision_enum"),
        nullable=False,
    )
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    result: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<AgentAuditLog id={self.id} agent={self.agent_name!r} "
            f"tool={self.tool_name!r} decision={self.decision.value}>"
        )
