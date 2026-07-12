"""Producer Contract Test — Architecture Guard Layer.

Scans Snapshot Producer files for forbidden operations defined in
architecture_rules.yaml.  A violation blocks the build.

When no producer files exist, all tests pass (clean state).

Run:
  pytest tests/contracts/test_producer_purity.py
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCER_DIR = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "analyst_workbench"
)


def _producer_files() -> list[Path]:
    if not PRODUCER_DIR.exists():
        return []
    return sorted(
        p for p in PRODUCER_DIR.rglob("*producer*.py")
        if not p.name.startswith("__")
    )


# ── Forbidden pattern detectors ─────────────────────────────────────

def _classify_detector(node: ast.AST) -> bool:
    """Detect business classification in if-statements or list comprehensions."""
    # Explicit if: if stage == 'fermentation': institution
    if isinstance(node, ast.If):
        for child in ast.walk(node.test):
            if isinstance(child, ast.Compare):
                for c in child.comparators:
                    if isinstance(c, ast.Constant) and isinstance(c.value, str):
                        if c.value in ("fermentation", "start", "divergence",
                                       "acceleration", "institution", "hot_money"):
                            return True
    # List comprehension with condition: [x for x in themes if x["score"] > 30]
    if isinstance(node, ast.ListComp):
        for gen in node.generators:
            for if_clause in gen.ifs:
                for child in ast.walk(if_clause):
                    if isinstance(child, ast.Compare):
                        for c in child.comparators:
                            if isinstance(c, ast.Constant) and isinstance(c.value, (int, float)):
                                return True  # numeric threshold = business rule
                            if isinstance(c, ast.Constant) and isinstance(c.value, str):
                                if c.value in ("fermentation", "start", "divergence",
                                               "acceleration"):
                                    return True
    return False


def _filter_detector(node: ast.AST) -> bool:
    """if name.startswith('【'): continue"""
    if not isinstance(node, ast.If):
        return False
    for child in ast.walk(node.test):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
            if child.func.attr in ("startswith", "isdigit"):
                return True
    return False


def _hardcoded_list_detector(node: ast.AST) -> bool:
    """NOISE = ('SpaceX', 'Token', ...)"""
    if not isinstance(node, ast.Assign):
        return False
    for target in node.targets:
        if isinstance(target, ast.Name):
            if any(kw in target.id.upper() for kw in
                   ("NOISE", "BLOCK", "FILTER", "PATTERN", "PREFIX", "ASHARE")):
                if isinstance(node.value, (ast.Tuple, ast.List)):
                    return True
    return False


def _fallback_detector(node: ast.AST) -> bool:
    """if not institution: institution = something_else"""
    if not isinstance(node, ast.If):
        return False
    for child in ast.walk(node.test):
        if isinstance(child, ast.UnaryOp) and isinstance(child.op, ast.Not):
            if isinstance(child.operand, ast.Name):
                if child.operand.id in ("institution", "hot_money", "data", "rows"):
                    return True
    return False


def _sorted_ranking_detector(node: ast.AST) -> bool:
    """Detect sorted(key=lambda x: x['strength_score']) — business ranking."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name) and node.func.id == "sorted":
        for kw in node.keywords:
            if kw.arg == "key" and kw.value is not None:
                return True  # sorted with business key = ranking
    return False


DETECTORS: list[tuple[str, callable]] = [
    ("classification_by_stage", _classify_detector),
    ("data_filtering", _filter_detector),
    ("hardcoded_pattern_list", _hardcoded_list_detector),
    ("fallback_to_alternate_source", _fallback_detector),
    ("sorted_business_ranking", _sorted_ranking_detector),
]


# ── Helpers ─────────────────────────────────────────────────────────

def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _scan(tree: ast.AST) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        for name, detector in DETECTORS:
            if detector(node):
                violations.append((getattr(node, "lineno", 0), name))
    return violations


# ── Tests ───────────────────────────────────────────────────────────

FILES = _producer_files()


@pytest.mark.skipif(not FILES, reason="No producer files — clean state")
@pytest.mark.parametrize("path", FILES)
def test_producer_has_no_forbidden_patterns(path: Path) -> None:
    tree = _parse(path)
    violations = _scan(tree)
    assert not violations, (
        f"Forbidden patterns in {path.name}:\n"
        + "\n".join(f"  line {ln}: {name}" for ln, name in violations)
        + "\n\nProducers must only map fields. "
        + "No classify, filter, hardcode, or fallback."
    )


@pytest.mark.skipif(not FILES, reason="No producer files — clean state")
def test_no_producer_references_recap_doc() -> None:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        assert "recap_doc" not in text, (
            f"{path.name} references recap_doc — forbidden by Section 8"
        )
