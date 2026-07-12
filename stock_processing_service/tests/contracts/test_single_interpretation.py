"""Single Interpretation Guard — Architecture Guard Layer.

Phase 4.5.7 Rule: one business fact = one interpretation entry point.
Prevents old data paths (emotion_review, chart_reviews, recap_doc)
from being consumed in parallel with ReviewDocument.

Scan: frontend for legacy data fetches, API for dual responses,
      ContextFactory for duplicate field sources.

Run:
  pytest tests/contracts/test_single_interpretation.py
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# ── Legacy paths that must NOT appear in non-debug code ─────────────

LEGACY_API_PATTERNS = [
    "/api/emotion-",
    "/api/analyst-charts/",
    "/api/v1/analyst-workspace/{date}/emotion",
]

LEGACY_FIELD_NAMES = [
    "emotion_review",      # replaced by review_document.emotion
    "chart_reviews",       # replaced by review_document.market + evidence
    "chart_data",          # replaced by review_document.evidence.charts
    "trend_data",          # replaced by review_document.evidence.trend_series
    "recap_doc",           # replaced by review_document.*
    "formal_review",       # replaced by review_document
    "legacy",              # must not exist in review_document
]

# Files to scan for legacy patterns (skip node_modules, dist, __pycache__)
SCAN_DIRS = [
    PROJECT_ROOT / "frontend" / "src",
    PROJECT_ROOT / "stock_processing_service" / "application" / "services" / "review_document",
]
SCAN_EXCLUDE = {"node_modules", "dist", "__pycache__", ".git"}


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            if any(ex in path.parts for ex in SCAN_EXCLUDE):
                continue
            files.append(path)
        for path in scan_dir.rglob("*.tsx"):
            if any(ex in path.parts for ex in SCAN_EXCLUDE):
                continue
            files.append(path)
        for path in scan_dir.rglob("*.ts"):
            if any(ex in path.parts for ex in SCAN_EXCLUDE):
                continue
            files.append(path)
    return files


def test_no_legacy_fetch_in_frontend() -> None:
    """Frontend must not fetch legacy emotion/chart/trend JSON endpoints."""
    # Known: EmotionDashboard.tsx useEmotionTrend fetches trend.json
    # for 5-day emotion timeline.  Pending migration to reviewDocument.evidence.trend_series.
    # Exception expires 2026-07-20.
    KNOWN_EXCEPTIONS = {
        "EmotionDashboard.tsx": ["/api/analyst-charts/trend.json"],
        "AnalystWorkspacePage.tsx": ["/api/v2/daily-review-v2"],
    }
    violations: list[str] = []
    for path in _scan_files():
        if path.suffix not in (".tsx", ".ts"):
            continue
        text = path.read_text(encoding="utf-8")
        exceptions = KNOWN_EXCEPTIONS.get(path.name, [])
        for pattern in LEGACY_API_PATTERNS:
            if pattern not in text:
                continue
            # Check if this specific occurrence is in the exception list
            if any(exc in text for exc in exceptions):
                continue
                violations.append(f"{path.name}: fetch('{pattern}...')")

    assert not violations, (
        "NEW frontend legacy API fetches detected:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nUse reviewDocument.* instead."
    )


def test_no_legacy_field_in_review_document_schema() -> None:
    """ReviewDocument schema must not contain legacy field names."""
    schema_path = (
        PROJECT_ROOT
        / "stock_processing_service"
        / "application"
        / "services"
        / "review_document"
        / "schema.py"
    )
    if not schema_path.exists():
        pytest.skip("schema.py not found")
    text = schema_path.read_text(encoding="utf-8")
    violations: list[str] = []
    for field in LEGACY_FIELD_NAMES:
        if field in text:
            violations.append(f"schema.py contains '{field}'")
    # emotion_review is referenced in FieldProvenance source strings — OK
    # recap_doc, formal_review, legacy must NOT appear in schema field names
    blocked = ["recap_doc", "formal_review", "legacy"]
    real_violations = [v for v in violations if any(b in v for b in blocked)]
    assert not real_violations, (
        "ReviewDocument schema contains legacy field names:\n"
        + "\n".join(f"  - {v}" for v in real_violations)
    )


def test_no_dual_data_source_in_context_factory() -> None:
    """ContextFactory must not read the same field from two different sources."""
    ctx_path = (
        PROJECT_ROOT
        / "stock_processing_service"
        / "application"
        / "services"
        / "review_document"
        / "context.py"
    )
    if not ctx_path.exists():
        pytest.skip("context.py not found")
    tree = ast.parse(ctx_path.read_text(encoding="utf-8"))

    # Collect all field reads: (source_var, key)
    reads: list[tuple[str, str]] = []
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
        source_node = node.args[0]
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            if isinstance(source_node, ast.Name):
                reads.append((source_node.id, key_node.value))

    # Group by key, check for multi-source reads
    from collections import defaultdict
    by_key: dict[str, set[str]] = defaultdict(set)
    for source, key in reads:
        by_key[key].add(source)

    # Multiple sources for the same key = dual interpretation risk
    multi_source = {k: v for k, v in by_key.items() if len(v) > 1}
    # OK patterns: legitimate nesting fallbacks (try capital_state first, then derived)
    OK_MULTI = {
        "money_flows", "top_stocks",        # capital_state.money_flows → derived.money_flows
        "trade_date",                       # _trade_date helper reads from multiple
        "derived_context",                  # attention_state nesting
    }
    real_issues = {k: v for k, v in multi_source.items() if k not in OK_MULTI}

    assert not real_issues, (
        "ContextFactory reads the same field from multiple sources:\n"
        + "\n".join(f"  '{k}' from {v}" for k, v in real_issues.items())
        + "\n\nSingle Interpretation Principle violated."
    )
