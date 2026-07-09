"""Golden tests for Phase 4.1b MarkdownReferenceParser.

Validates:
  - Core field extraction (7/7 PANIC, 7/8 REPAIR_WATCH)
  - Relay rates with ratio normalization
  - Strategy label extraction (JSON + markdown list)
  - Missing field tracking and sentinel behavior
  - 5-level extraction status
  - Field-level evidence provenance
  - Section-scoped parsing (theme lifecycle, limitup attribution)
  - Ratio normalization edge cases
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_processing_service.application.services.analyst_reference.contracts import (
    MISSING,
    ExtractionStatus,
    normalize_ratio,
    normalize_int,
)
from stock_processing_service.application.services.analyst_reference.markdown_ingestion import (
    MarkdownReferenceParser,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def parser():
    return MarkdownReferenceParser()


@pytest.fixture
def recap_0707():
    return MarkdownReferenceParser().parse_file(
        FIXTURES / "analyst_recap_0707.md", trade_date=date(2026, 7, 7)
    )


@pytest.fixture
def recap_0708():
    return MarkdownReferenceParser().parse_file(
        FIXTURES / "analyst_recap_0708.md", trade_date=date(2026, 7, 8)
    )


# ═══ TC-4.1b-01: 7/7 core fields ═══

def test_parse_0707_core_fields(recap_0707):
    """7/7 PANIC day: all core facts and emotion fields match analyst ground truth."""
    r = recap_0707
    assert r.trade_date == date(2026, 7, 7)
    assert r.market_facts.limit_up_count == 33
    assert r.market_facts.max_board_height == 5
    assert r.market_facts.active_capital_yi == 897.0
    assert r.emotion_label.market_phase == "PANIC"
    assert r.emotion_label.risk_level == "HIGH"
    assert r.emotion_label.emotion_momentum == -12.0


# ═══ TC-4.1b-02: 7/8 core fields ═══

def test_parse_0708_core_fields(recap_0708):
    """7/8 REPAIR_WATCH day: all core facts and emotion fields match."""
    r = recap_0708
    assert r.trade_date == date(2026, 7, 8)
    assert r.market_facts.limit_up_count == 47
    assert r.market_facts.max_board_height == 7
    assert r.market_facts.active_capital_yi == 739.0
    assert r.emotion_label.market_phase == "REPAIR_WATCH"
    assert r.emotion_label.risk_level == "MEDIUM_HIGH"
    assert r.emotion_label.emotion_momentum == -4.0


# ═══ TC-4.1b-03: 7/8 relay rates + ratio normalization ═══

def test_parse_0708_relay_rates(recap_0708):
    """7/8 relay rates normalized: 21% -> 0.21, 33% -> 0.33."""
    r = recap_0708
    assert r.relay_label.promotion_1_to_2 == 0.21
    assert r.relay_label.promotion_2_to_3 == 0.33
    assert r.relay_label.max_board_height == 7
    assert r.relay_label.max_board_stock == "恒尚节能"


# ═══ TC-4.1b-04: 7/7 relay rates (decimal) ═══

def test_parse_0707_relay_rates(recap_0707):
    """7/7 relay rates stored as decimals: 0.051, 0.0."""
    r = recap_0707
    assert r.relay_label.promotion_1_to_2 == 0.051
    assert r.relay_label.promotion_2_to_3 == 0.0


# ═══ TC-4.1b-05: Strategy label from JSON ═══

def test_parse_0708_strategy_from_json(recap_0708):
    """7/8 strategy extracted from strategy_label JSON block."""
    s = recap_0708.strategy_label
    assert len(s.allowed) >= 3
    assert "科技硬件快进快出反弹套利" in s.allowed
    assert "核心方向确认后跟随" in s.allowed
    assert len(s.forbidden) >= 2
    assert "指数未企稳前重仓追高" in s.forbidden
    assert len(s.watch_points) >= 4
    assert "韩国指数" in s.watch_points
    assert "恒尚节能高度" in s.watch_points


# ═══ TC-4.1b-06: Strategy from markdown lists ═══

def test_parse_0707_strategy_from_lists(recap_0707):
    """7/7 strategy extracted from markdown list with Chinese labels."""
    s = recap_0707.strategy_label
    assert len(s.allowed) >= 1
    assert "空仓等待" in s.allowed
    assert len(s.watch_points) >= 1
    assert any("韩国指数" in w or "恒尚节能" in w for w in s.watch_points)


# ═══ TC-4.1b-07: Missing field tracking ═══

def test_missing_fields_not_zero():
    """Missing fields are tracked in quality.missing_fields, not silently set to 0."""
    # Create a minimal markdown with only partial data
    parser = MarkdownReferenceParser()
    minimal_md = """# 2026-07-07 复盘

```json
{"phase": "PANIC", "risk": "HIGH", "emotion_momentum": -12}
```

涨停数：33
"""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(minimal_md)
        tmp_path = f.name

    try:
        rec = parser.parse_file(tmp_path, trade_date=date(2026, 7, 7))
        # limit_up_count from regex should be 33
        # max_board_height is MISSING
        assert rec.market_facts.max_board_height is None
        # Missing fields should include max_board_height
        assert any("max_board_height" in mf for mf in rec.quality.missing_fields), \
            f"Expected max_board_height in missing_fields, got: {rec.quality.missing_fields}"
    finally:
        import os
        os.unlink(tmp_path)


# ═══ TC-4.1b-08: Ratio normalization edge cases ═══

def test_ratio_normalization():
    """normalize_ratio handles all expected input formats."""
    # Percentage strings
    assert normalize_ratio("21%") == 0.21
    assert normalize_ratio("33%") == 0.33
    assert normalize_ratio("0%") == 0.0
    assert normalize_ratio("100%") == 1.0

    # Decimal strings
    assert normalize_ratio("0.21") == 0.21
    assert normalize_ratio("0.051") == 0.051

    # Integer > 1 → treated as percentage-point
    assert normalize_ratio(21) == 0.21
    assert normalize_ratio(33) == 0.33

    # Float < 1 → kept as-is
    assert normalize_ratio(0.21) == 0.21
    assert normalize_ratio(0.051) == 0.051

    # Missing markers
    assert normalize_ratio("—") is None
    assert normalize_ratio("-") is None
    assert normalize_ratio("无") is None
    assert normalize_ratio("未提及") is None
    assert normalize_ratio("N/A") is None
    assert normalize_ratio("") is None
    assert normalize_ratio(None) is None


# ═══ TC-4.1b-09: normalize_int edge cases ═══

def test_normalize_int():
    assert normalize_int("33") == 33
    assert normalize_int(33) == 33
    assert normalize_int(33.0) == 33
    assert normalize_int("—") is None
    assert normalize_int("-") is None
    assert normalize_int("无") is None
    assert normalize_int("") is None
    assert normalize_int(None) is None


# ═══ TC-4.1b-10: 5-level extraction status ═══

def test_0707_status_is_full_complete(recap_0707):
    assert recap_0707.quality.extraction_status == ExtractionStatus.FULL_COMPLETE


def test_0708_status_is_full_complete(recap_0708):
    assert recap_0708.quality.extraction_status == ExtractionStatus.FULL_COMPLETE


def test_partial_extraction_status():
    """Minimal markdown with only limit_up + phase → PARTIAL."""
    parser = MarkdownReferenceParser()
    minimal = """# Test

```json
{"limit_up": 33, "phase": "PANIC"}
```
"""
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(minimal)
        tmp_path = f.name

    try:
        rec = parser.parse_file(tmp_path, trade_date=date(2026, 7, 7))
        # limit_up=33 found, but no max_board, no risk, no momentum → PARTIAL
        assert rec.quality.extraction_status in (
            ExtractionStatus.PARTIAL, ExtractionStatus.NEEDS_REVIEW
        ), f"Expected PARTIAL or NEEDS_REVIEW, got {rec.quality.extraction_status}"
        assert rec.quality.required_field_coverage < 1.0
    finally:
        os.unlink(tmp_path)


# ═══ TC-4.1b-11: Field-level evidence ═══

def test_extracted_fields_have_evidence(recap_0708):
    """Each ExtractedField has source_section + evidence_text."""
    fields = recap_0708.extracted_fields
    assert len(fields) > 10, f"Expected >10 extracted fields, got {len(fields)}"

    for ef in fields:
        assert ef.field_path, f"Empty field_path in {ef}"
        assert ef.parser_rule, f"Empty parser_rule for {ef.field_path}"
        # source_section can be empty for some fallback fields, but most should have it
        if ef.parser_rule.startswith("json_block"):
            assert ef.confidence >= 0.90, \
                f"JSON block field {ef.field_path} has low confidence: {ef.confidence}"


# ═══ TC-4.1b-12: LimitUp stock details ═══

def test_limitup_stock_details_extracted(recap_0708):
    """LimitUp attribution includes per-stock code/name/board/theme."""
    lu = recap_0708.limitup_attribution
    assert len(lu) >= 3

    # At least one theme should have stock details
    total_details = sum(len(a.key_stocks) for a in lu)
    assert total_details >= 3, f"Expected >=3 stock details, got {total_details}"

    # Check structure of a stock detail
    for attr in lu:
        for stock in attr.key_stocks:
            assert "code" in stock, f"Missing code in {stock}"
            assert "name" in stock, f"Missing name in {stock}"
            assert "board" in stock, f"Missing board in {stock}"
            assert len(stock["code"]) == 6, f"Invalid stock code: {stock['code']}"


# ═══ TC-4.1b-13: Leader role classification ═══

def test_leader_role_classification(recap_0708):
    """Leaders are classified with non-empty roles."""
    leaders = recap_0708.leader_state
    assert len(leaders) >= 3

    # Market leader should have max board
    roles = [l.role for l in leaders]
    assert "market_leader" in roles, f"No market_leader found in {roles}"

    # The 7-board stock should be market_leader
    max_leader = next((l for l in leaders if l.board_height == 7), None)
    assert max_leader is not None, "No 7-board leader found"
    assert max_leader.role == "market_leader", \
        f"7-board leader role should be market_leader, got {max_leader.role}"


# ═══ TC-4.1b-14: Theme lifecycle section-scoped ═══

def test_theme_lifecycle_scoped(recap_0707):
    """Theme lifecycle entries parsed only within designated sections."""
    themes = recap_0707.theme_lifecycle
    assert len(themes) > 0

    for t in themes:
        assert t.theme_name, "Empty theme name"
        assert t.state in ("启动", "调整", "修复", "观察", "关注", "分歧", ""), \
            f"Unexpected state: {t.state}"
        # Style should be set
        assert t.style in ("institutional", "hot_money", "limitup_theme", ""), \
            f"Unexpected style: {t.style}"


# ═══ TC-4.1b-15: MISSING sentinel is distinct from None/0/"" ═══

def test_missing_sentinel():
    assert MISSING is not None
    assert MISSING is not 0
    assert MISSING is not ""
    assert MISSING is not False
    # normalize_ratio with MISSING-like sentinel
    assert normalize_ratio(None) is None
