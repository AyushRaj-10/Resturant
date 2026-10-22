"""Agent discovery router providing read-only inspection of available tools."""

from typing import Any, Dict, List
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from app.agents.tools.registry import clean_schema_for_llm, list_tools

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
