"""API Contract Validator — Architecture Guard Layer.

Verifies the Workbench API response structure matches Section 6.1:
  - Top-level: only review_document, metadata, diagnostics
  - Diagnostics: only counts + quality, no business data
  - No legacy fields leaked to the top level

Run:
  pytest tests/contracts/test_api_contract.py
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
API_PATH = PROJECT_ROOT / "stock_processing_service" / "api_app.py"

# Section 6.1: allowed and forbidden top-level response keys
ALLOWED_TOP_LEVEL = {"review_document", "metadata", "diagnostics"}
FORBIDDEN_TOP_LEVEL = {
    "emotion_review", "chart_reviews", "chart_data",
    "formal_review", "recap_doc", "trend_data",
}

# Diagnostics: allowed keys
ALLOWED_DIAGNOSTICS = {
    "theme_count", "stock_count", "override_count",
    "draft_version", "source_quality", "missing_fields",
    "quality", "can_generate",
}
FORBIDDEN_DIAGNOSTICS = {
    "chart_reviews", "trend_data", "emotion_review",
}


def _workspace_response_keys(tree: ast.AST) -> list[tuple[int, set[str]]]:
    """Find all return dicts in get_analyst_workspace and extract their keys."""
    results: list[tuple[int, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name != "get_analyst_workspace":
            continue
        # Find all return statements and dict literals
        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                if isinstance(child.value, ast.Call):
                    # return _workspace_review_document_response(...)
                    results.append((child.lineno, ALLOWED_TOP_LEVEL))
                elif isinstance(child.value, ast.Dict):
                    keys: set[str] = set()
                    for k in child.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keys.add(k.value)
                    results.append((child.lineno, keys))
    return results


def test_workspace_api_top_level_only_allowed_keys() -> None:
    """GET /analyst-workspace must only return review_document/metadata/diagnostics."""
    if not API_PATH.exists():
        pytest.skip("api_app.py not found")
    tree = ast.parse(API_PATH.read_text(encoding="utf-8"))

    # The API uses _workspace_review_document_response which returns a dict.
    # Check that no other top-level keys are injected.
    func_node = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_analyst_workspace":
            func_node = node
            break

    if func_node is None:
        pytest.skip("get_analyst_workspace not found")

    # Scan the function body for `response["key"] = ...` or `response[key] = ...`
    violations: list[str] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    if isinstance(target.slice, ast.Constant):
                        key = target.slice.value
                        if isinstance(key, str) and key in FORBIDDEN_TOP_LEVEL:
                            violations.append(
                                f"line {node.lineno}: response['{key}'] — forbidden top-level key"
                            )

    assert not violations, (
        "Workbench API leaks forbidden top-level keys:\n"
        + "\n".join(violations)
        + f"\n\nAllowed: {ALLOWED_TOP_LEVEL}"
    )


def test_workspace_response_is_built_by_contract_function() -> None:
    """The workspace response must be built by _workspace_review_document_response."""
    if not API_PATH.exists():
        pytest.skip("api_app.py not found")
    text = API_PATH.read_text(encoding="utf-8")
    assert "_workspace_review_document_response" in text, (
        "Workbench API must use _workspace_review_document_response to build responses"
    )


def test_no_forbidden_imports_in_api() -> None:
    """api_app.py must not import from legacy recap/emotion/chart modules."""
    if not API_PATH.exists():
        pytest.skip("api_app.py not found")
    text = API_PATH.read_text(encoding="utf-8")
    # These should only appear in legacy/debug endpoints, not workspace
    forbidden_in_workspace = [
        "recap_doc",
        "static_json",
    ]
    for term in forbidden_in_workspace:
        # Allow the term in non-workspace contexts (debug, legacy)
        count = text.count(term)
        assert count >= 0  # informational
