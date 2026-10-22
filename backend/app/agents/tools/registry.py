"""Tool registry, discovery, Groq-compatible LLM schema export, and execution pipeline."""

import copy
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ValidationError
from app.agents.tools.base import RiskLevel, ToolContext, ToolError, ToolResult, ToolSpec
from app.agents.tools.definitions import TOOL_DEFINITIONS
from app.services.exceptions import ConflictError, NotFoundError, ValidationRuleError

logger = logging.getLogger(__name__)

# Primary lookup mapping of tool name -> ToolSpec
TOOLS: Dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_DEFINITIONS}


def get_tool(name: str) -> Optional[ToolSpec]:
    """Retrieve a ToolSpec by its unique name."""
    return TOOLS.get(name)


def list_tools(
    risk: Optional[RiskLevel] = None,
    names: Optional[Set[str]] = None,
) -> List[ToolSpec]:
    """List registered tools with optional risk and allowlist filters."""
    tools = list(TOOLS.values())
    if risk is not None:
        tools = [t for t in tools if t.risk == risk]
    if names is not None:
        tools = [t for t in tools if t.name in names]
    return tools


def clean_schema_for_llm(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Inline $defs references and enforce additionalProperties=false recursively for LLMs."""
    defs = schema.get("$defs", {})

    def _resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_key = node["$ref"].split("/")[-1]
                if ref_key in defs:
                    resolved = copy.deepcopy(defs[ref_key])
                    if "description" in node:
                        resolved["description"] = node["description"]
                    return _resolve(resolved)
            cleaned = {}
            for k, v in node.items():
                if k in {"$defs", "title"}:
                    continue
                cleaned[k] = _resolve(v)
            if cleaned.get("type") == "object" or "properties" in cleaned:
                cleaned["additionalProperties"] = False
            return cleaned
        elif isinstance(node, list):
            return [_resolve(item) for item in node]
        return node

    cleaned_schema = _resolve(copy.deepcopy(schema))
    if cleaned_schema.get("type") == "object" or "properties" in cleaned_schema:
        cleaned_schema["additionalProperties"] = False
    return cleaned_schema


def to_llm_tool_specs(names: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
    """Export tool definitions in OpenAI/Groq function-calling JSON format."""
    tools = list_tools(names=names)
    specs: List[Dict[str, Any]] = []
    for tool in tools:
        raw_schema = tool.args_model.model_json_schema()
        cleaned_schema = clean_schema_for_llm(raw_schema)
        specs.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": cleaned_schema,
            },
        })
    return specs


# =========================================================================
# Execution Pipeline (Two-Stage Architecture with Step 11 Guard Hook Point)
# =========================================================================

def _prepare_call(
    name: str,
    raw_args: Dict[str, Any],
) -> Tuple[Optional[ToolSpec], Optional[BaseModel], Optional[ToolResult]]:
    """Stage 1: Tool lookup and strict argument validation against args_model."""
    tool = get_tool(name)
    if tool is None:
        return None, None, ToolResult(
            ok=False,
            error=ToolError(
                type="unknown_tool",
                message=f"Unknown tool '{name}'. Available tools: {', '.join(sorted(TOOLS.keys()))}",
            ),
        )

    try:
        validated_args = tool.args_model.model_validate(raw_args if raw_args is not None else {})
        return tool, validated_args, None
    except ValidationError as exc:
        errors_summary = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", []))
            msg = err.get("msg", "Invalid value")
            errors_summary.append(f"{loc}: {msg}" if loc else msg)
        readable_msg = f"Invalid arguments for tool '{name}': {'; '.join(errors_summary)}"
        return tool, None, ToolResult(
            ok=False,
            error=ToolError(
                type="invalid_arguments",
                message=readable_msg,
            ),
        )


def _run_call(ctx: ToolContext, tool: ToolSpec, args: BaseModel) -> ToolResult:
    """Stage 2: Handler execution with error mapping and automatic DB rollback on failure."""
    try:
        data = tool.handler(ctx, args)
        return ToolResult(ok=True, data=data, error=None)
    except NotFoundError as exc:
        ctx.db.rollback()
        return ToolResult(
            ok=False,
            error=ToolError(type="not_found", message=str(exc)),
        )
    except ValidationRuleError as exc:
        ctx.db.rollback()
        return ToolResult(
            ok=False,
            error=ToolError(type="validation", message=str(exc)),
        )
    except ConflictError as exc:
        ctx.db.rollback()
        return ToolResult(
            ok=False,
            error=ToolError(type="conflict", message=str(exc)),
        )
    except Exception as exc:
        ctx.db.rollback()
        logger.exception("Unexpected error executing tool '%s': %s", tool.name, exc)
        return ToolResult(
            ok=False,
            error=ToolError(
                type="internal",
                message="An internal error occurred while executing the tool.",
            ),
        )


def execute_tool(ctx: ToolContext, name: str, raw_args: Dict[str, Any]) -> ToolResult:
    """Execute an agent tool with strict arguments, safe isolation, and zero exceptions raised."""
    # -------------------------------------------------------------------------
    # Stage 1: Preparation (lookup + strict argument validation)
    # -------------------------------------------------------------------------
    tool, validated_args, prep_error = _prepare_call(name, raw_args)
    if prep_error is not None:
        return prep_error

    # =========================================================================
    # [STEP 11 HOOK POINT: GUARD APPROVAL & AUDIT LOGGING WILL GO HERE]
    # In Step 11, the guard layer will evaluate (ctx, tool, validated_args)
    # to enforce pre-call permission checks, human confirmations, and audit logs
    # before proceeding to handler execution.
    # =========================================================================

    # -------------------------------------------------------------------------
    # Stage 2: Execution (handler dispatch + domain error mapping)
    # -------------------------------------------------------------------------
    return _run_call(ctx, tool, validated_args)
