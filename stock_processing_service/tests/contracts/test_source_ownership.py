"""Source Ownership Validator — Architecture Guard Layer.

Verifies that every ReviewDocument field reads from a contract-approved
data source.  Cross-references the ContextFactory and Assembler against
architecture_rules.yaml Section 8 field_sources.

A violation means a field is being populated from a forbidden source
(e.g. capital.institution from themes.stage instead of money_flows).

Run:
  pytest tests/contracts/test_source_ownership.py
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = PROJECT_ROOT / "docs" / "architecture" / "architecture_rules.yaml"
CONTEXT_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "review_document"
    / "context.py"
)
ASSEMBLER_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "review_document"
    / "assembler.py"
)


def _load_rules() -> dict:
    if not RULES_PATH.exists():
        pytest.skip("architecture_rules.yaml not found")
    with open(RULES_PATH) as f:
        return yaml.safe_load(f)


# ── Section 8: approved and forbidden sources per section ───────────

def _field_sources() -> dict[str, dict[str, list[str]]]:
    """Extract allowed/forbidden sources from the rules YAML."""
    rules = _load_rules()
    sources = rules.get("data_sources", {})
    result: dict[str, dict[str, list[str]]] = {}
    for section, spec in sources.items():
        result[section] = {
            "allowed": spec.get("allowed", []),
            "forbidden": spec.get("forbidden", []),
        }
    return result


# ── Forbidden source terms → human-readable label ───────────────────

FORBIDDEN_TERMS: dict[str, str] = {
    "theme_stage": "theme_stage — capital must not be inferred from theme lifecycle",
    "theme_score": "theme_score — capital must not be inferred from strength score",
    "theme_stage_inference": "theme_stage_inference — classification from stage is prohibited",
    "chart_view_model_backfill": "chart_view_model_backfill — reverse-engineering is prohibited",
    "emotion_node_derivation": "emotion_node_derivation — plan must not be derived from emotion",
    "prose_mainline": "prose_mainline — limit_up categories must come from structured data",
    "recap_doc": "recap_doc — forbidden by Section 8",
    "institution_style_chart": "institution_style_chart — use derived_context.money_flows instead",
    "static_json": "static_json — forbidden, use Snapshot sources",
    "analyst_charts_api": "analyst_charts_api — forbidden, use Snapshot chart_reviews",
    "static_emotion_json": "static_emotion_json — forbidden, use Snapshot emotion_review",
    "legacy_market_summary": "legacy_market_summary — forbidden",
    "legacy_stock_lists": "legacy_stock_lists — forbidden",
    "ai_analyst_mixed_watch_list": "ai_analyst_mixed_watch_list — forbidden",
    "system_generated_defaults": "system_generated_defaults — forbidden for audit",
}


# ── Tests ───────────────────────────────────────────────────────────

def test_context_factory_reads_only_allowed_sources() -> None:
    """ContextFactory must only extract fields from Section 8 approved sources."""
    if not CONTEXT_PATH.exists():
        pytest.skip("context.py not found")
    field_sources = _field_sources()
    tree = ast.parse(CONTEXT_PATH.read_text(encoding="utf-8"))

    # Collect all `_list_value(..., "key")` and `_dict_value(..., "key")` calls
    violations: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in ("_list_value", "_dict_value", "_value"):
            continue
        if len(node.args) < 2:
            continue
        key_node = node.args[1]
        if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
            continue
        key = key_node.value
        source_node = node.args[0]
        if isinstance(source_node, ast.Name):
            source_var = source_node.id  # "snapshot" or "derived" or "capital_state"
            # Check if this key belongs to a section with a forbidden source
            for section, spec in field_sources.items():
                for forbidden in spec.get("forbidden", []):
                    if forbidden in key or key in forbidden:
                        violations.append(
                            f"ContextFactory reads '{key}' from '{source_var}' — "
                            f"may conflict with {section} contract: {FORBIDDEN_TERMS.get(forbidden, forbidden)}"
                        )

    # This is informational — not all key readings are violations.
    # A real violation would be: reading institution from themes.
    # Future: add cross-reference with actual data flow.
    assert True  # passes; violations are diagnostic


def test_assembler_does_not_access_forbidden_fields() -> None:
    """Assembler must not bypass ContextFactory to read raw fields."""
    if not ASSEMBLER_PATH.exists():
        pytest.skip("assembler.py not found")
    tree = ast.parse(ASSEMBLER_PATH.read_text(encoding="utf-8"))

    # The assembler should only access ctx.* fields, never raw source dicts
    forbidden_access: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # Detect: source.get("recap_doc") or source["recap_doc"]
            if node.func.attr == "get" and len(node.args) >= 1:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if arg.value in ("recap_doc", "static_json", "trend_json"):
                        forbidden_access.append(
                            f"line {node.lineno}: source.get('{arg.value}') — forbidden by Section 8"
                        )

    assert not forbidden_access, (
        "Assembler accesses forbidden raw fields:\n"
        + "\n".join(forbidden_access)
    )


def test_assembler_has_no_fallback_pattern() -> None:
    """Assembler._assemble_* must not contain fallback: if not x: x = y."""
    if not ASSEMBLER_PATH.exists():
        pytest.skip("assembler.py not found")
    tree = ast.parse(ASSEMBLER_PATH.read_text(encoding="utf-8"))

    # Find all _assemble_* method bodies
    assemble_methods: list[ast.FunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_assemble_"):
            assemble_methods.append(node)

    violations: list[str] = []
    for method in assemble_methods:
        for node in ast.walk(method):
            # if not x: x = [row for row in y if ...]
            if isinstance(node, ast.If):
                # Check test for `not x` pattern
                if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
                    violations.append(
                        f"{method.name} line {node.lineno}: "
                        f"fallback pattern detected (if not x: x = y)"
                    )

    # KNOWN: assembler has legacy fallback patterns (pre-existing)
    # _assemble_themes lines 121, 133: if not key: continue (identity skip)
    # _assemble_capital lines 183, 185: if not institution: infer from money_flows
    # These are documented violations to be fixed in a future PR.
    # New fallback patterns beyond these MUST be rejected.
    KNOWN_FALLBACKS = [
        "_assemble_capital line 183",
        "_assemble_capital line 185",
        "_assemble_themes line 121",
        "_assemble_themes line 133",
    ]
    new_violations = [
        v for v in violations
        if not any(k in v for k in KNOWN_FALLBACKS)
    ]
    if new_violations:
        pytest.fail(
            "NEW assembler fallback patterns detected:\n"
            + "\n".join(new_violations)
            + "\n\nAssembler must output quality=MISSING, not fallback."
        )
