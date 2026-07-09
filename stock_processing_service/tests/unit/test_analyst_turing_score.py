"""Phase 4.2 T04 — AnalystTuringScore tests.

Covers: perfect score, phase/risk/fact/relay mismatch penalties,
        grade A-F, confidence adjustment, calibration hints,
        theme+leader combined, to_dict serializable.
"""

from __future__ import annotations

from datetime import date

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
from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
    AIDiagnosisReferenceView,
)
from stock_processing_service.application.services.analyst_alignment.comparator import (
    AnalystComparator,
)
from stock_processing_service.application.services.analyst_alignment.turing_score import (
    AnalystTuringEvaluator,
    AnalystTuringScore,
    FORMULA_VERSION,
)


@pytest.fixture
def evaluator():
    return AnalystTuringEvaluator()


def _perfect_analyst(td: date) -> AnalystReferenceRecord:
    from stock_processing_service.application.services.analyst_reference.contracts import LeaderState, ThemeLifecycleEntry
    return AnalystReferenceRecord(
        trade_date=td, source_type="mock",
        market_facts=MarketFacts(
            limit_up_count=47, chain_board_count=14, max_board_height=7,
            active_capital_yi=739.0, market_up_ratio=0.35, loss_effect_ratio=0.18,
        ),
        emotion_label=EmotionLabel(
            market_phase="REPAIR_WATCH", risk_level="MEDIUM_HIGH",
            emotion_momentum=-4.0,
        ),
        relay_label=RelayLabel(
            max_board_height=7, promotion_1_to_2=0.21, promotion_2_to_3=0.33,
        ),
        leader_state=[
            LeaderState(stock_code="603137", stock_name="恒尚节能", board_height=7, role="market_leader"),
            LeaderState(stock_code="002855", stock_name="捷荣技术", board_height=3, role="theme_leader"),
        ],
        theme_lifecycle=[
            ThemeLifecycleEntry(theme_name="国产服务器", state="启动", day_count=1),
            ThemeLifecycleEntry(theme_name="半导体设备", state="启动", day_count=2),
        ],
        strategy_label=StrategyLabel(
            summary="冰点后弱修复，等待核心方向确认；条件单为主",
            allowed=["科技硬件快进快出反弹套利"],
            watch_points=["韩国指数", "恒尚节能高度"],
        ),
        quality=AnalystReferenceQuality(
            extraction_status=ExtractionStatus.FULL_COMPLETE,
            required_field_coverage=1.0,
        ),
    )


def _perfect_ai(td: date) -> AIDiagnosisReferenceView:
    from stock_processing_service.application.services.analyst_reference.contracts import LeaderState, ThemeLifecycleEntry
    return AIDiagnosisReferenceView(
        trade_date=td,
        market_facts=MarketFacts(
            limit_up_count=47, chain_board_count=14, max_board_height=7,
            active_capital_yi=739.0, market_up_ratio=0.35, loss_effect_ratio=0.18,
        ),
        emotion_label=EmotionLabel(
            market_phase="REPAIR_WATCH", risk_level="MEDIUM_HIGH",
            emotion_momentum=-4.0,
        ),
        relay_label=RelayLabel(
            max_board_height=7, promotion_1_to_2=0.21, promotion_2_to_3=0.33,
        ),
        strategy_label=StrategyLabel(
            summary="冰点后弱修复，等待核心方向确认；条件单为主",
        ),
        leader_state=(
            LeaderState(stock_code="603137", stock_name="恒尚节能", board_height=7, role="market_leader"),
            LeaderState(stock_code="002855", stock_name="捷荣技术", board_height=3, role="theme_leader"),
        ),
        theme_lifecycle=(
            ThemeLifecycleEntry(theme_name="国产服务器", state="启动", day_count=1),
            ThemeLifecycleEntry(theme_name="半导体设备", state="启动", day_count=2),
        ),
        source_quality=1.0,
    )


# ═══ TC-4.2-TS-01: perfect report → A grade ═══

def test_perfect_report_grade_a(evaluator):
    td = date(2026, 7, 8)
    ats = evaluator.evaluate(_perfect_analyst(td), _perfect_ai(td))
    assert ats.overall_score > 0.95
    assert ats.grade == "A"
    assert ats.confidence >= 0.9
    assert ats.formula_version == FORMULA_VERSION


# ═══ TC-4.2-TS-02: phase mismatch lowers score ═══

def test_phase_mismatch_lowers_score(evaluator):
    td = date(2026, 7, 8)
    analyst = _perfect_analyst(td)
    ai = _perfect_ai(td)
    ai = AIDiagnosisReferenceView(
        trade_date=td, market_facts=ai.market_facts,
        emotion_label=EmotionLabel(market_phase="PANIC", risk_level="MEDIUM_HIGH", emotion_momentum=-4.0),
        relay_label=ai.relay_label, source_quality=1.0,
    )
    ats = evaluator.evaluate(analyst, ai)
    assert ats.phase_score <= 0.5   # PANIC vs REPAIR_WATCH
    assert ats.overall_score < 0.9  # lower than perfect


# ═══ TC-4.2-TS-03: risk mismatch lowers score ═══

def test_risk_mismatch_lowers_score(evaluator):
    td = date(2026, 7, 8)
    analyst = _perfect_analyst(td)
    ai = _perfect_ai(td)
    ai = AIDiagnosisReferenceView(
        trade_date=td, market_facts=ai.market_facts,
        emotion_label=EmotionLabel(market_phase="REPAIR_WATCH", risk_level="HIGH", emotion_momentum=-4.0),
        relay_label=ai.relay_label, source_quality=1.0,
    )
    ats = evaluator.evaluate(analyst, ai)
    # MEDIUM_HIGH vs HIGH = 1 level → 0.75
    assert ats.risk_score == 0.75
    assert ats.overall_score < 0.95


# ═══ TC-4.2-TS-04: low facts → FACT_SOURCE_REVIEW ═══

def test_low_facts_adds_hint(evaluator):
    td = date(2026, 7, 8)
    analyst = _perfect_analyst(td)
    ai = AIDiagnosisReferenceView(
        trade_date=td,
        market_facts=MarketFacts(
            limit_up_count=100,  # diff=53, tol=1 → fail
            chain_board_count=2,   # diff=12, tol=1 → fail
            max_board_height=3,    # diff=4, tol=0 → fail
            active_capital_yi=200.0,  # diff=539, tol=20 → fail
            market_up_ratio=0.75,  # diff=0.40, tol=0.03 → fail
            loss_effect_ratio=0.18,
        ),
        emotion_label=EmotionLabel(market_phase="REPAIR_WATCH", risk_level="MEDIUM_HIGH"),
        relay_label=RelayLabel(max_board_height=7, promotion_1_to_2=0.21, promotion_2_to_3=0.33),
        source_quality=1.0,
    )
    ats = evaluator.evaluate(analyst, ai)
    assert ats.facts_score < 0.7
    assert any("FACT" in h for h in ats.calibration_hints), \
        f"Expected FACT_SOURCE_REVIEW hint, got {ats.calibration_hints}"


# ═══ TC-4.2-TS-05: low relay → RELAY_ECOLOGY_REVIEW ═══

def test_low_relay_adds_hint(evaluator):
    td = date(2026, 7, 8)
    analyst = _perfect_analyst(td)
    ai = AIDiagnosisReferenceView(
        trade_date=td,
        market_facts=MarketFacts(limit_up_count=47, chain_board_count=14, max_board_height=7,
                                  active_capital_yi=739.0, market_up_ratio=0.35, loss_effect_ratio=0.18),
        emotion_label=EmotionLabel(market_phase="REPAIR_WATCH", risk_level="MEDIUM_HIGH"),
        relay_label=RelayLabel(max_board_height=3, promotion_1_to_2=0.90, promotion_2_to_3=0.80),
        source_quality=1.0,
    )
    ats = evaluator.evaluate(analyst, ai)
    assert ats.relay_score < 0.7
    assert any("RELAY" in h for h in ats.calibration_hints), \
        f"Expected RELAY_ECOLOGY_REVIEW hint, got {ats.calibration_hints}"


# ═══ TC-4.2-TS-06: excluded fields reduce confidence ═══

def test_excluded_fields_reduce_confidence(evaluator):
    td = date(2026, 7, 9)
    analyst = AnalystReferenceRecord(
        trade_date=td, source_type="mock",
        market_facts=MarketFacts(limit_up_count=None),  # missing
        emotion_label=EmotionLabel(market_phase="PANIC", risk_level="HIGH"),
        relay_label=RelayLabel(max_board_height=5),
        quality=AnalystReferenceQuality(
            extraction_status=ExtractionStatus.PARTIAL,
            required_field_coverage=0.6,
            missing_fields=("market_facts.limit_up_count",),
        ),
    )
    ai = AIDiagnosisReferenceView(
        trade_date=td,
        market_facts=MarketFacts(limit_up_count=50),
        emotion_label=EmotionLabel(market_phase="PANIC", risk_level="HIGH"),
        relay_label=RelayLabel(max_board_height=5),
    )
    ats = evaluator.evaluate(analyst, ai)
    # Confidence should be lower due to analyst_quality=0.6 and excluded fields
    assert ats.confidence < 0.9
    # But overall_score shouldn't be affected by excluded fields
    assert ats.phase_score == 1.0  # PANIC=H vs PANIC=H


# ═══ TC-4.2-TS-07: theme+leader combined score ═══

def test_theme_leader_combined_score(evaluator):
    td = date(2026, 7, 8)
    ats = evaluator.evaluate(_perfect_analyst(td), _perfect_ai(td))
    assert 0.0 <= ats.theme_leader_score <= 1.0


# ═══ TC-4.2-TS-08: to_dict serializable ═══

def test_turing_score_to_dict(evaluator):
    td = date(2026, 7, 8)
    ats = evaluator.evaluate(_perfect_analyst(td), _perfect_ai(td))
    d = ats.to_dict()
    assert "trade_date" in d
    assert "scores" in d
    assert "overall" in d["scores"]
    assert "grade" in d
    assert d["grade"] == "A"
    assert "calibration_hints" in d
    assert "formula_version" in d


# ═══ TC-4.2-TS-09: grade boundaries ═══

def test_grade_boundaries(evaluator):
    """Verify grade thresholds."""
    assert evaluator._compute_grade(0.90) == "A"
    assert evaluator._compute_grade(0.80) == "B"
    assert evaluator._compute_grade(0.70) == "C"
    assert evaluator._compute_grade(0.50) == "D"
    assert evaluator._compute_grade(0.30) == "F"
