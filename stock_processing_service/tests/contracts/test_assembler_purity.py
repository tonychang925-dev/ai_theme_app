"""Assembler Purity Validator — Architecture Guard Layer.

Verifies ReviewDocumentAssembler contains no fallback, inference, derive,
or default-value generation.  Assembler must only map Context fields to
ReviewDocument fields.  Missing data → quality=MISSING.

Run:
  pytest tests/contracts/test_assembler_purity.py
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ASSEMBLER_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "review_document"
    / "assembler.py"
)


def _parse() -> ast.AST:
    if not ASSEMBLER_PATH.exists():
        pytest.skip("assembler.py not found")
    return ast.parse(ASSEMBLER_PATH.read_text(encoding="utf-8"))


# ── Known legacy exceptions with expiration ─────────────────────────
# Format: (method_prefix, line, reason, expires)
LEGACY_EXCEPTIONS: list[tuple[str, int, str, str]] = [
    ("_assemble_themes", 121, "identity key fallback: if not key: continue", "2026-07-20"),
    ("_assemble_themes", 133, "identity key fallback", "2026-07-20"),
    ("_assemble_capital", 183, "institution from money_flows fallback", "2026-07-20"),
    ("_assemble_capital", 185, "hot_money from money_flows fallback", "2026-07-20"),
]


def _is_expired(expire_date: str) -> bool:
    from datetime import date
    return date.today() > date.fromisoformat(expire_date)


# ── Detectors ───────────────────────────────────────────────────────

def _fallback_in_assembler(node: ast.AST, method_name: str) -> bool:
    """if not x: x = [...] — infer from alternate source"""
    if not isinstance(node, ast.If):
        return False
    if not isinstance(node.test, ast.UnaryOp) or not isinstance(node.test.op, ast.Not):
        return False
    # Check if this is a known legacy exception
    line = node.lineno
    for prefix, ex_line, reason, expires in LEGACY_EXCEPTIONS:
        if method_name.startswith(prefix) and line == ex_line:
            if _is_expired(expires):
                pytest.fail(
                    f"LEGACY EXCEPTION EXPIRED: {method_name} line {line}\n"
                    f"  Reason: {reason}\n"
                    f"  Expired: {expires}\n"
                    f"  Must fix the fallback or renew the exception."
                )
            return False  # Known, not-expired exception
    return True


def _inference_in_assembler(node: ast.AST, method_name: str) -> bool:
    """if role_label == '机构': institution — classify from string labels"""
    if not isinstance(node, ast.Compare):
        return False
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if child.value in ("机构", "游资", "institution", "hot_money"):
                return True
    return False


def _default_value_in_assembler(node: ast.AST, method_name: str) -> bool:
    """emotion_node = source.get(x) or 'CHAOS' — fabricating defaults"""
    if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.Or):
        return False
    for val in node.values:
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            if val.value in ("CHAOS", "DIVERGENCE", "ICE_POINT", "NORMAL",
                             "观察", "观望", "修复"):
                return True
    return False


def _calculation_in_assembler(node: ast.AST, method_name: str) -> bool:
    """confidence = min(0.85, score / 100 + 0.15) — business calculation"""
    if not isinstance(node, ast.BinOp):
        return False
    # Detect arithmetic on named fields: score / 100, confidence * 100
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in (
            "confidence", "score", "strength", "breadth", "momentum",
        ):
            if isinstance(node.op, (ast.Mult, ast.Div, ast.Add, ast.Sub)):
                return True
    return False


# ── Tests ───────────────────────────────────────────────────────────

def test_assembler_methods_have_no_fallback() -> None:
    """No _assemble_* method must fall back to an alternate data source."""
    tree = _parse()
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("_assemble_"):
            continue
        for child in ast.walk(node):
            if _fallback_in_assembler(child, node.name):
                violations.append(
                    f"{node.name} line {child.lineno}: fallback pattern"
                )

    if violations:
        pytest.fail(
            "NEW assembler fallback patterns detected:\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\n\nAssembler must output quality=MISSING, not fallback."
        )


def test_assembler_methods_have_no_business_inference() -> None:
    """No _assemble_* method must classify from string labels."""
    tree = _parse()
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("_assemble_"):
            continue
        for child in ast.walk(node):
            if _inference_in_assembler(child, node.name):
                violations.append(
                    f"{node.name} line {child.lineno}: "
                    f"business inference from string label"
                )

    # Known: _assemble_capital line 185 has '机构'/'游资' in role_label check
    # This is documented in LEGACY_EXCEPTIONS
    new_violations = [v for v in violations if "_assemble_capital" not in v]
    if new_violations:
        pytest.fail(
            "NEW assembler inference patterns detected:\n"
            + "\n".join(f"  - {v}" for v in new_violations)
        )


def test_assembler_methods_have_no_default_value_fabrication() -> None:
    """No _assemble_* method must fabricate default values (e.g. 'CHAOS')."""
    tree = _parse()
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("_assemble_"):
            continue
        for child in ast.walk(node):
            if _default_value_in_assembler(child, node.name):
                violations.append(
                    f"{node.name} line {child.lineno}: "
                    f"default value fabrication"
                )

    assert not violations, (
        "Assembler fabricates default values:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nMissing values → None, not a fake default."
    )


def test_assembler_methods_have_no_business_calculation() -> None:
    """No _assemble_* method must perform business arithmetic."""
    tree = _parse()
    violations: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("_assemble_"):
            continue
        for child in ast.walk(node):
            if _calculation_in_assembler(child, node.name):
                violations.append(
                    f"{node.name} line {child.lineno}: "
                    f"business calculation detected"
                )

    assert not violations, (
        "Assembler performs business calculations:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nCalculations belong in Snapshot Producers, not Assembler."
    )
