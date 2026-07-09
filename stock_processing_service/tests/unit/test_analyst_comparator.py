"""Phase 4.2 T03 — AnalystComparator tests.

Covers: exact match, tolerance, missing analyst/AI, conflict,
        phase compatible, risk distance, keyword overlap,
        smoke test with real fixtures.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from stock_processing_service.application.services.analyst_reference.contracts import (
    AnalystReferenceQuality,
    AnalystReferenceRecord,
    EmotionLabel,
    ExtractionStatus,
    MarketFacts,
    RelayLabel,
    StrategyLabel,
)
from stock_processing_service.application.services.analyst_reference.markdown_ingestion import (
    MarkdownReferenceParser,
)
from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
    AIDiagnosisReferenceView,
)
from stock_processing_service.application.services.analyst_alignment.comparator import (
    AnalystComparator,
)
from stock_processing_service.application.services.analyst_alignment.contracts import (
    AnalystAlignmentReport,
    DiffType,
    MatchType,
    MetricDiff,
    SemanticDiff,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def comparator():
    return AnalystComparator()


@pytest.fixture
def analyst_0708():
    return MarkdownReferenceParser().parse_file(
        FIXTURES / "analyst_recap_0708.md", trade_date=date(2026, 7, 8)
    )


# ═══ Helpers ═══

def _ai_view_0708_matched() -> AIDiagnosisReferenceView:
    """AI view that matches the 7/8 analyst reference closely."""
    from stock_processing_service.application.services.analyst_reference.contracts import LeaderState, ThemeLifecycleEntry
    return AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 8),
        market_facts=MarketFacts(
            limit_up_count=47, chain_board_count=14, max_board_height=7,
            active_capital_yi=739.0, market_up_ratio=0.35, loss_effect_ratio=0.18,
        ),
        emotion_label=EmotionLabel(
            market_phase="REPAIR_WATCH", risk_level="MEDIUM_HIGH",
            emotion_momentum=-4.0,
        ),
        relay_label=RelayLabel(
            max_board_height=7, max_board_stock="恒尚节能",
            promotion_1_to_2=0.21, promotion_2_to_3=0.33,
        ),
        strategy_label=StrategyLabel(
            summary="冰点后弱修复，等待核心方向确认；条件单为主，不扩大仓位",
            allowed=["科技硬件快进快出反弹套利"],
            watch_points=["韩国指数", "恒尚节能高度"],
        ),
        leader_state=(
            LeaderState(stock_code="603137", stock_name="恒尚节能", board_height=7, role="market_leader"),
            LeaderState(stock_code="002855", stock_name="捷荣技术", board_height=3, role="theme_leader"),
            LeaderState(stock_code="600105", stock_name="永鼎股份", board_height=2, role="pioneer"),
        ),
        theme_lifecycle=(
            ThemeLifecycleEntry(theme_name="国产服务器", state="启动", day_count=1),
            ThemeLifecycleEntry(theme_name="半导体设备", state="启动", day_count=2),
        ),
        source_quality=1.0,
    )


# ═══ TC-4.2-CMP-01: exact facts match ═══

def test_exact_facts_match(comparator, analyst_0708):
    ai = _ai_view_0708_matched()
    report = comparator.compare(analyst_0708, ai)
    assert report.facts_score >= 0.95
    for d in report.fact_diffs:
        if not d.excluded_from_score:
            assert d.passed, f"{d.field_path} should pass: {d.reason}"
            assert d.score >= 0.99


# ═══ TC-4.2-CMP-02: numeric within tolerance ═══

def test_numeric_within_tolerance(comparator, analyst_0708):
    ai = _ai_view_0708_matched()
    # Slight deviation for active_capital: 739 vs 750 → diff=11, tol=20 → passed
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 8),
        market_facts=MarketFacts(
            limit_up_count=47, chain_board_count=14, max_board_height=7,
            active_capital_yi=750.0,  # diff=11, within tol_abs=20
            market_up_ratio=0.35, loss_effect_ratio=0.18,
        ),
        emotion_label=EmotionLabel(market_phase="REPAIR_WATCH", risk_level="MEDIUM_HIGH", emotion_momentum=-4.0),
        relay_label=RelayLabel(max_board_height=7, promotion_1_to_2=0.21, promotion_2_to_3=0.33),
        source_quality=1.0,
    )
    report = comparator.compare(analyst_0708, ai)
    capital_diff = [d for d in report.fact_diffs if "active_capital" in d.field_path][0]
    assert capital_diff.passed
    assert capital_diff.score >= 0.6


# ═══ TC-4.2-CMP-03: numeric outside tolerance ═══

def test_numeric_outside_tolerance(comparator, analyst_0708):
    ai = _ai_view_0708_matched()
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 8),
        market_facts=MarketFacts(
            limit_up_count=55,  # diff=8, tol=1 → fail
            chain_board_count=14, max_board_height=7,
            active_capital_yi=739.0, market_up_ratio=0.35, loss_effect_ratio=0.18,
        ),
        emotion_label=EmotionLabel(market_phase="REPAIR_WATCH", risk_level="MEDIUM_HIGH", emotion_momentum=-4.0),
        relay_label=RelayLabel(max_board_height=7, promotion_1_to_2=0.21, promotion_2_to_3=0.33),
        source_quality=1.0,
    )
    report = comparator.compare(analyst_0708, ai)
    lu_diff = [d for d in report.fact_diffs if "limit_up_count" in d.field_path][0]
    assert not lu_diff.passed
    assert lu_diff.score < 0.6


# ═══ TC-4.2-CMP-04: missing analyst field ═══

def test_missing_analyst_excluded(comparator):
    analyst = AnalystReferenceRecord(
        trade_date=date(2026, 7, 9),
        source_type="mock",
        market_facts=MarketFacts(limit_up_count=None, max_board_height=None),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(),
        quality=AnalystReferenceQuality(
            extraction_status=ExtractionStatus.PARTIAL,
            missing_fields=("market_facts.limit_up_count",),
        ),
    )
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 9),
        market_facts=MarketFacts(limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(),
    )
    report = comparator.compare(analyst, ai)
    lu_diff = [d for d in report.fact_diffs if "limit_up_count" in d.field_path][0]
    assert lu_diff.diff_type == DiffType.MISSING_ANALYST
    assert lu_diff.excluded_from_score


# ═══ TC-4.2-CMP-05: missing AI field ═══

def test_missing_ai_scores_zero(comparator):
    analyst = AnalystReferenceRecord(
        trade_date=date(2026, 7, 9),
        source_type="mock",
        market_facts=MarketFacts(limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(),
        quality=AnalystReferenceQuality(extraction_status=ExtractionStatus.CORE_COMPLETE),
    )
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 9),
        market_facts=MarketFacts(limit_up_count=None),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(),
        missing_fields=("market_facts.limit_up_count",),
    )
    report = comparator.compare(analyst, ai)
    lu_diff = [d for d in report.fact_diffs if "limit_up_count" in d.field_path][0]
    assert lu_diff.diff_type == DiffType.MISSING_AI
    assert not lu_diff.excluded_from_score
    assert lu_diff.score == 0.0


# ═══ TC-4.2-CMP-06: reference conflict excluded ═══

def test_reference_conflict_excluded(comparator):
    analyst = AnalystReferenceRecord(
        trade_date=date(2026, 7, 9),
        source_type="mock",
        market_facts=MarketFacts(limit_up_count=46, max_board_height=5),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(),
        quality=AnalystReferenceQuality(
            extraction_status=ExtractionStatus.CORE_COMPLETE,
            low_confidence_fields=("market_facts.limit_up_count",),
        ),
    )
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 9),
        market_facts=MarketFacts(limit_up_count=48),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(),
    )
    report = comparator.compare(analyst, ai)
    lu_diff = [d for d in report.fact_diffs if "limit_up_count" in d.field_path][0]
    assert lu_diff.diff_type == DiffType.REFERENCE_CONFLICT
    assert lu_diff.excluded_from_score


# ═══ TC-4.2-CMP-07: phase exact match ═══

def test_phase_exact_match(comparator, analyst_0708):
    ai = _ai_view_0708_matched()
    report = comparator.compare(analyst_0708, ai)
    phase_diff = [d for d in report.emotion_diffs if "market_phase" in d.field_path][0]
    assert isinstance(phase_diff, SemanticDiff)
    assert phase_diff.match_type == MatchType.EXACT
    assert phase_diff.score == 1.0


# ═══ TC-4.2-CMP-08: phase compatible — PANIC vs REPAIR_WATCH ═══

def test_phase_compatible_panic_vs_repair_watch(comparator):
    """Analyst says PANIC, AI says REPAIR_WATCH → NEAR_MISS, score=0.5."""
    analyst_panic = AnalystReferenceRecord(
        trade_date=date(2026, 7, 8), source_type="mock",
        market_facts=MarketFacts(limit_up_count=33, max_board_height=5),
        emotion_label=EmotionLabel(market_phase="PANIC", risk_level="HIGH", emotion_momentum=-12.0),
        relay_label=RelayLabel(max_board_height=5),
        quality=AnalystReferenceQuality(extraction_status=ExtractionStatus.CORE_COMPLETE),
    )
    ai_repair = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 8),
        market_facts=MarketFacts(limit_up_count=33, max_board_height=5),
        emotion_label=EmotionLabel(market_phase="REPAIR_WATCH", risk_level="HIGH", emotion_momentum=-4.0),
        relay_label=RelayLabel(max_board_height=5),
        source_quality=1.0,
    )
    report = comparator.compare(analyst_panic, ai_repair)
    phase_diff = [d for d in report.emotion_diffs if "market_phase" in d.field_path][0]
    assert isinstance(phase_diff, SemanticDiff)
    assert phase_diff.match_type in (MatchType.NEAR_MISS, MatchType.COMPATIBLE)
    assert phase_diff.score == 0.5


# ═══ TC-4.2-CMP-09: risk one-level difference ═══

def test_risk_one_level_difference(comparator):
    analyst = AnalystReferenceRecord(
        trade_date=date(2026, 7, 9), source_type="mock",
        market_facts=MarketFacts(limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(market_phase="REPAIR_WATCH", risk_level="HIGH"),
        relay_label=RelayLabel(max_board_height=5),
        quality=AnalystReferenceQuality(extraction_status=ExtractionStatus.CORE_COMPLETE),
    )
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 9),
        market_facts=MarketFacts(limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(market_phase="REPAIR_WATCH", risk_level="MEDIUM_HIGH"),
        relay_label=RelayLabel(max_board_height=5),
        source_quality=1.0,
    )
    report = comparator.compare(analyst, ai)
    risk_diff = [d for d in report.emotion_diffs if "risk_level" in d.field_path][0]
    assert isinstance(risk_diff, SemanticDiff)
    assert risk_diff.match_type == MatchType.COMPATIBLE
    assert risk_diff.score == 0.75


# ═══ TC-4.2-CMP-10: overall_score aggregation ═══

def test_overall_score_aggregation(comparator, analyst_0708):
    ai = _ai_view_0708_matched()
    report = comparator.compare(analyst_0708, ai)
    assert 0.0 <= report.overall_score <= 1.0
    # Close match should give high score (not 100% — themes/leaders are Jaccard)
    assert report.overall_score > 0.8
    # Core scores should be near-perfect
    assert report.facts_score > 0.9
    assert report.emotion_score > 0.9
    assert report.relay_score > 0.9


# ═══ TC-4.2-CMP-11: report JSON serializable ═══

def test_report_to_dict(comparator, analyst_0708):
    ai = _ai_view_0708_matched()
    report = comparator.compare(analyst_0708, ai)
    d = report.to_dict()
    assert "trade_date" in d
    assert "scores" in d
    assert "overall" in d["scores"]
    assert len(d["fact_diffs"]) == 6
    assert len(d["emotion_diffs"]) >= 2


# ═══ TC-4.2-CMP-12: smoke test with real fixture ═══

def test_smoke_0708_fixture(comparator, analyst_0708):
    """Full comparison with real 7/8 analyst fixture and matched AI view."""
    ai = _ai_view_0708_matched()
    report = comparator.compare(analyst_0708, ai)
    assert isinstance(report, AnalystAlignmentReport)
    assert report.trade_date == date(2026, 7, 8)
    # All scores should be high for matched data
    assert report.facts_score >= 0.9
    assert report.relay_score >= 0.9
    assert report.emotion_score >= 0.9
    assert report.overall_score >= 0.80  # core facts/relay/emotion ~1.0, themes/leaders lower via Jaccard


# ═══ TC-4.2-CMP-13: metrics-only mode doesn't penalize missing phase ═══

def test_metrics_only_phase_not_penalized(comparator, analyst_0708):
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 8),
        market_facts=MarketFacts(limit_up_count=47, chain_board_count=14, max_board_height=7,
                                  active_capital_yi=739.0, market_up_ratio=0.35, loss_effect_ratio=0.18),
        emotion_label=EmotionLabel(market_phase="", risk_level="", emotion_momentum=-4.0),
        relay_label=RelayLabel(max_board_height=7, promotion_1_to_2=0.21, promotion_2_to_3=0.33),
        source_quality=0.6,  # metrics-only quality
        missing_fields=("emotion_label.market_phase", "emotion_label.risk_level"),
    )
    report = comparator.compare(analyst_0708, ai)
    phase_diff = [d for d in report.emotion_diffs if "market_phase" in d.field_path][0]
    assert isinstance(phase_diff, SemanticDiff)
    # Metrics-only should exclude phase from scoring
    assert phase_diff.excluded_from_score


# ═══ TC-4.2-CMP-14: keyword overlap strategy scoring ═══

def test_strategy_keyword_overlap(comparator):
    analyst = AnalystReferenceRecord(
        trade_date=date(2026, 7, 9), source_type="mock",
        market_facts=MarketFacts(limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(market_phase="PANIC", risk_level="HIGH"),
        relay_label=RelayLabel(max_board_height=5),
        strategy_label=StrategyLabel(allowed=["科技硬件快进快出反弹套利"], watch_points=["韩国指数", "恒尚节能高度"]),
        quality=AnalystReferenceQuality(extraction_status=ExtractionStatus.CORE_COMPLETE),
    )
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 9),
        market_facts=MarketFacts(limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(market_phase="PANIC", risk_level="HIGH"),
        relay_label=RelayLabel(max_board_height=5),
        strategy_label=StrategyLabel(summary="科技硬件反弹套利，关注韩国指数"),
        source_quality=1.0,
    )
    report = comparator.compare(analyst, ai)
    # Should find keyword overlap
    assert len(report.strategy_diffs) > 0
    strat_diff = report.strategy_diffs[0]
    assert isinstance(strat_diff, SemanticDiff)
    assert strat_diff.score >= 0.3  # some overlap on "科技硬件", "反弹套利", "韩国指数"


# ═══ TC-4.2-CMP-15: leader overlap Jaccard ═══

def test_leader_overlap(comparator, analyst_0708):
    ai = _ai_view_0708_matched()
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 8),
        market_facts=ai.market_facts,
        emotion_label=ai.emotion_label,
        relay_label=ai.relay_label,
        leader_state=(
            __import__("stock_processing_service.application.services.analyst_reference.contracts", fromlist=["LeaderState"]).LeaderState(
                stock_code="603137", stock_name="恒尚节能", board_height=7, role="market_leader"),
            __import__("stock_processing_service.application.services.analyst_reference.contracts", fromlist=["LeaderState"]).LeaderState(
                stock_code="002855", stock_name="捷荣技术", board_height=3, role="theme_leader"),
        ),
        source_quality=1.0,
    )
    report = comparator.compare(analyst_0708, ai)
    assert len(report.leader_diffs) > 0
    leader_diff = report.leader_diffs[0]
    assert leader_diff.score > 0.0


# ═══ TC-4.2-T03.1-01: tolerance OR logic — pct passes when abs fails ═══

def test_numeric_tolerance_or_logic_pct_passes(comparator):
    """1000 vs 1030: abs=30 > 20, pct=3% <= 5% → should PASS via OR."""
    analyst = AnalystReferenceRecord(
        trade_date=date(2026, 7, 9), source_type="mock",
        market_facts=MarketFacts(active_capital_yi=1000.0, limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(max_board_height=5),
        quality=AnalystReferenceQuality(extraction_status=ExtractionStatus.CORE_COMPLETE),
    )
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 9),
        market_facts=MarketFacts(active_capital_yi=1030.0, limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(max_board_height=5),
    )
    report = comparator.compare(analyst, ai)
    cap_diff = [d for d in report.fact_diffs if "active_capital" in d.field_path][0]
    assert cap_diff.passed, \
        f"Expected OR logic: abs=30>20 but pct=3%<=5% should pass. diff={cap_diff}"


# ═══ TC-4.2-T03.1-02: MISSING_AI → DATA_ERROR ═══

def test_missing_ai_classified_as_data_error(comparator):
    """MISSING_AI should be DATA_ERROR, not REFERENCE_WEAK."""
    analyst = AnalystReferenceRecord(
        trade_date=date(2026, 7, 9), source_type="mock",
        market_facts=MarketFacts(limit_up_count=50, max_board_height=5),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(max_board_height=5),
        quality=AnalystReferenceQuality(extraction_status=ExtractionStatus.CORE_COMPLETE),
    )
    ai = AIDiagnosisReferenceView(
        trade_date=date(2026, 7, 9),
        market_facts=MarketFacts(limit_up_count=None),
        emotion_label=EmotionLabel(),
        relay_label=RelayLabel(max_board_height=5),
        missing_fields=("market_facts.limit_up_count",),
    )
    report = comparator.compare(analyst, ai)
    # MISSING_AI should appear as DATA_ERROR, not REFERENCE_WEAK
    from stock_processing_service.application.services.analyst_alignment.contracts import ErrorType
    assert ErrorType.DATA_ERROR in report.error_types, \
        f"Expected DATA_ERROR for MISSING_AI, got {report.error_types}"
    assert ErrorType.REFERENCE_WEAK not in report.error_types, \
        f"MISSING_AI should NOT be REFERENCE_WEAK, got {report.error_types}"
