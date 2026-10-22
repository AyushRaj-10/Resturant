"""Security boundary tests verifying strict separation between LLM text generation and system execution.

Ensures:
- app/llm/ contains ZERO imports from services, models, database, or routers.
- app/llm/ contains ZERO tool/function-calling parameters (tools, tool_choice, functions).
- app/services/ai_features.py never invokes mutating order service functions.
"""

import ast
from pathlib import Path
import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

BACKEND_APP = Path(__file__).resolve().parent.parent.parent / "backend" / "app"


def test_app_llm_no_forbidden_imports():
    """Verify no file in app/llm imports from services, models, database, or routers."""
    llm_dir = BACKEND_APP / "llm"
    forbidden_prefixes = ("app.services", "app.models", "app.database", "app.routers")

    for py_file in llm_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_prefixes:
                        assert not alias.name.startswith(forbidden), (
                            f"Forbidden import '{alias.name}' in {py_file.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_prefixes:
                        assert not node.module.startswith(forbidden), (
                            f"Forbidden from-import '{node.module}' in {py_file.name}"
                        )


def test_app_llm_no_tool_calling_parameters():
    """Verify app/llm does not declare or accept tool/function calling parameters."""
    llm_dir = BACKEND_APP / "llm"
    forbidden_args = {"tools", "tool_choice", "functions", "function_call"}

    for py_file in llm_dir.glob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                arg_names = {a.arg for a in node.args.args + node.args.kwonlyargs}
                overlap = arg_names.intersection(forbidden_args)
                assert not overlap, f"Function '{node.name}' in {py_file.name} accepts forbidden tool args: {overlap}"


def test_ai_features_does_not_call_mutating_order_services():
    """Verify ai_features.py NEVER invokes create, update, cancel, or delete order service methods."""
    ai_features_file = BACKEND_APP / "services" / "ai_features.py"
    content = ai_features_file.read_text(encoding="utf-8")
    tree = ast.parse(content, filename=str(ai_features_file))

    mutating_methods = {
        "create_order",
        "update_item_quantity",
        "update_bill",
        "change_order_status",
        "cancel_order",
        "delete_order",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check attribute calls like order_service.create_order(...)
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in mutating_methods, (
                    f"ai_features.py illegally invokes mutating service method: {node.func.attr}"
                )
            # Check direct function calls like create_order(...)
            elif isinstance(node.func, ast.Name):
                assert node.func.id not in mutating_methods, (
                    f"ai_features.py illegally invokes mutating service function: {node.func.id}"
                )
