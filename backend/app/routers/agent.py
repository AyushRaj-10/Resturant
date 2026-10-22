"""Agent router providing read-only tool discovery and multi-agent chat endpoints."""

from typing import Any, Dict, List
import uuid
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.agents.orchestrator import handle_message
from app.agents.tools.registry import clean_schema_for_llm, list_tools
from app.database import get_db
from app.routers.rate_limiter import check_ai_rate_limit
from app.schemas.agent import AgentChatRequest, AgentChatResponse

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
    )
