"""M4c: EvidenceFusionEngine unit tests.

Covers: single-source scoring, multi-source resonance, decay, cninfo age gate.
"""

from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.domain.services.evidence_fusion import (
    CNINFO_MAX_AGE_DAYS,
    DAILY_DECAY,
    RESEARCH_MAX_AGE_DAYS,
    RESEARCH_MAX_CONTRIBUTION,
    RESONANCE_BONUS,
    EvidenceFusionEngine,
    EvidenceItem,
)

TD = date(2026, 6, 18)


def _item(src: str, theme: str, code="000811", name="冰轮环境",
          ev_date=TD, reason="", conf=1.0, tags=None) -> EvidenceItem:
    return EvidenceItem(
        source_name=src, theme_name=theme,
        stock_code=code, stock_name=name,
        evidence_date=ev_date, reason=reason or f"{src} evidence",
        confidence=conf, tags=tags or [],
    )


# ── Single-source scoring ───────────────────────────────────────

def test_single_ths_scores_1_0():
    engine = EvidenceFusionEngine()
    items = [_item("ths", "AI算力基础设施", reason="数据中心液冷")]
    results = engine.fuse(TD, items)
    assert len(results) == 1
    assert results[0].evidence_score == 1.0
    assert results[0].source_count == 1
    assert not results[0].is_resonance


def test_single_jyhf_scores_0_35():
    engine = EvidenceFusionEngine()
    items = [_item("jyhf", "AI算力基础设施")]
    results = engine.fuse(TD, items)
    assert results[0].evidence_score == pytest.approx(0.35)


def test_single_eastmoney_scores_0_45():
    engine = EvidenceFusionEngine()
    items = [_item("eastmoney", "AI算力基础设施")]
    results = engine.fuse(TD, items)
    assert results[0].evidence_score == pytest.approx(0.45)


# ── Multi-source resonance ──────────────────────────────────────

def test_two_source_resonance_bonus():
    """THS + CNInfo → 1.00 + 0.80 + 0.20 resonance = 2.00."""
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "AI算力基础设施", reason="数据中心液冷"),
        _item("cninfo", "AI算力基础设施", reason="重大合同签署"),
    ]
    results = engine.fuse(TD, items)
    assert len(results) == 1
    expected = 1.00 + 0.80 + RESONANCE_BONUS[2]  # 2.00
    assert results[0].evidence_score == pytest.approx(expected)
    assert results[0].source_count == 2
    assert results[0].is_resonance
    assert "ths" in results[0].evidence_sources
    assert "cninfo" in results[0].evidence_sources


def test_three_source_resonance():
    """THS + CNInfo + Eastmoney → 1.00+0.80+0.45+0.30 = 2.55 -> capped at 2.00."""
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "机器人", reason="人形机器人"),
        _item("cninfo", "机器人", reason="战略合作协议"),
        _item("eastmoney", "机器人"),
    ]
    results = engine.fuse(TD, items)
    assert results[0].source_count == 3
    assert results[0].is_resonance
    # 1.00 + 0.80 + 0.45 + 0.30 = 2.55, capped at 2.00
    assert results[0].evidence_score == 2.00


def test_four_source_full_resonance():
    """All 4 sources agree → capped at 2.00."""
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "PCB/HBM产业链"),
        _item("cninfo", "PCB/HBM产业链"),
        _item("eastmoney", "PCB/HBM产业链"),
        _item("jyhf", "PCB/HBM产业链"),
    ]
    results = engine.fuse(TD, items)
    assert results[0].source_count == 4
    assert results[0].evidence_score == 2.00


# ── CNInfo age gate ─────────────────────────────────────────────

def test_cninfo_expired_is_skipped():
    """CNInfo older than 3 days should be excluded."""
    engine = EvidenceFusionEngine()
    old_date = TD - __import__("datetime").timedelta(days=CNINFO_MAX_AGE_DAYS + 1)
    items = [
        _item("ths", "AI算力基础设施", reason="液冷"),
        _item("cninfo", "AI算力基础设施", ev_date=old_date, reason="旧公告"),
    ]
    results = engine.fuse(TD, items)
    # Only THS counts → no resonance
    assert results[0].source_count == 1
    assert results[0].evidence_score == 1.00
    assert not results[0].is_resonance


def test_cninfo_within_3_days_counts():
    """CNInfo within 3 days should be included."""
    engine = EvidenceFusionEngine()
    recent = TD - __import__("datetime").timedelta(days=2)
    items = [
        _item("ths", "AI算力基础设施", reason="液冷"),
        _item("cninfo", "AI算力基础设施", ev_date=recent, reason="合同公告"),
    ]
    results = engine.fuse(TD, items)
    assert results[0].source_count == 2
    assert results[0].is_resonance


# ── Decay ───────────────────────────────────────────────────────

def test_decay_reduces_older_evidence():
    engine = EvidenceFusionEngine()
    old = TD - __import__("datetime").timedelta(days=2)
    items = [
        _item("ths", "AI算力基础设施", reason="液冷"),
        _item("eastmoney", "AI算力基础设施", ev_date=old),
    ]
    results = engine.fuse(TD, items)
    decayed_weight = 0.45 * (DAILY_DECAY ** 2)  # eastmoney 2 days decay
    expected = 1.00 + decayed_weight + RESONANCE_BONUS[2]
    assert results[0].evidence_score == pytest.approx(round(expected, 3))
    # THS is same-day (freshness 1.0), but eastmoney is 2 days old
    assert results[0].evidence_score < (1.00 + 0.45 + RESONANCE_BONUS[2])  # decayed


# ── Primary reason ──────────────────────────────────────────────

def test_primary_reason_from_highest_priority():
    engine = EvidenceFusionEngine()
    items = [
        _item("jyhf", "AI算力基础设施", reason="subject map"),
        _item("ths", "AI算力基础设施", reason="数据中心液冷"),
        _item("cninfo", "AI算力基础设施", reason="重大合同"),
    ]
    results = engine.fuse(TD, items)
    # THS has highest priority
    assert "数据中心液冷" in results[0].primary_reason


# ── Multiple stocks and themes ──────────────────────────────────

def test_multiple_stocks_and_themes():
    """冰轮环境→AI算力 + 埃斯顿→机器人."""
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "AI算力基础设施", "000811", "冰轮环境", reason="液冷"),
        _item("cninfo", "AI算力基础设施", "000811", "冰轮环境", reason="收购"),
        _item("ths", "机器人", "002747", "埃斯顿", reason="人形机器人"),
        _item("eastmoney", "机器人", "002747", "埃斯顿"),
        _item("jyhf", "机器人", "002747", "埃斯顿"),
    ]
    results = engine.fuse(TD, items)
    assert len(results) == 2

    ai_result = next(r for r in results if r.theme_name == "AI算力基础设施")
    assert ai_result.stock_code == "000811"
    assert ai_result.source_count == 2

    robot_result = next(r for r in results if r.theme_name == "机器人")
    assert robot_result.stock_code == "002747"
    assert robot_result.source_count == 3
    assert robot_result.is_resonance


# ── Score cap ───────────────────────────────────────────────────

def test_score_capped_at_2_0():
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "机器人", reason="人形机器人"),
        _item("cninfo", "机器人", reason="合作协议"),
        _item("eastmoney", "机器人"),
        _item("jyhf", "机器人"),
    ]
    results = engine.fuse(TD, items)
    # Uncapped: 1.00+0.80+0.45+0.35+0.50=3.10, capped to 2.00
    assert results[0].evidence_score == 2.00


# ── Empty / no evidence ─────────────────────────────────────────

# ── M4d: EPS expectation evidence ──────────────────────────────

def test_eps_contributes_expectation_score():
    """EPS evidence should contribute to expectation_score, not event_score."""
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "AI算力基础设施", reason="液冷"),
        _item("eps", "AI算力基础设施", reason="EPS增速+35%"),
    ]
    results = engine.fuse(TD, items)
    assert results[0].source_count == 2
    assert results[0].expectation_score > 0
    assert results[0].event_score > 0  # THS contributes to event
    # Total score should include both
    assert results[0].evidence_score > results[0].event_score


def test_eps_alone_has_zero_event_score():
    """EPS-only evidence should have 0 event_score."""
    engine = EvidenceFusionEngine()
    items = [_item("eps", "AI算力基础设施", reason="EPS+50%")]
    results = engine.fuse(TD, items)
    assert results[0].source_count == 1
    assert results[0].expectation_score == pytest.approx(0.70)
    assert results[0].event_score == 0.0


def test_five_source_full_resonance():
    """All 5 sources → 5-source resonance bonus."""
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "机器人"),
        _item("eps", "机器人"),
        _item("cninfo", "机器人"),
        _item("eastmoney", "机器人"),
        _item("jyhf", "机器人"),
    ]
    results = engine.fuse(TD, items)
    assert results[0].source_count == 5
    assert results[0].evidence_score == 2.00  # capped
    assert results[0].expectation_score > 0
    assert results[0].event_score > 0


# ── M5b: Research evidence ──────────────────────────────────────

def test_research_source_weight():
    """Research reports contribute 0.55 weight."""
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "AI算力基础设施", reason="液冷"),
        _item("research", "AI算力基础设施", reason="中信证券买入"),
    ]
    results = engine.fuse(TD, items)
    # 1.00 + 0.55(capped to 0.30) + 0.20 resonance = 1.50
    assert results[0].source_count == 2
    assert results[0].is_resonance
    assert results[0].evidence_score >= 1.50


def test_research_contributes_to_event_score():
    """Research is an event source, not expectation."""
    engine = EvidenceFusionEngine()
    items = [_item("research", "AI算力基础设施", reason="买入评级")]
    results = engine.fuse(TD, items)
    assert results[0].event_score == pytest.approx(0.55)
    assert results[0].expectation_score == 0.0


def test_six_source_full_resonance():
    """All 6 sources → capped at 2.00."""
    engine = EvidenceFusionEngine()
    items = [
        _item("ths", "机器人"),
        _item("eps", "机器人"),
        _item("cninfo", "机器人"),
        _item("eastmoney", "机器人"),
        _item("jyhf", "机器人"),
        _item("research", "机器人"),
    ]
    results = engine.fuse(TD, items)
    assert results[0].source_count == 6
    assert results[0].evidence_score == 2.00


# ── M5b.1 Research Quality Gate ─────────────────────────────────

def test_research_aged_out_is_skipped():
    """Research older than 30 days should be excluded."""
    engine = EvidenceFusionEngine()
    old_date = TD - __import__("datetime").timedelta(days=RESEARCH_MAX_AGE_DAYS + 1)
    items = [
        _item("ths", "AI算力基础设施", reason="液冷"),
        _item("research", "AI算力基础设施", ev_date=old_date, reason="旧研报"),
    ]
    results = engine.fuse(TD, items)
    assert results[0].source_count == 1  # research excluded
    assert results[0].evidence_score == 1.00


def test_research_capped_contribution():
    """Multiple research reports should not exceed cap."""
    engine = EvidenceFusionEngine()
    items = [
        _item("research", "AI算力基础设施", reason="买入"),
        _item("research", "AI算力基础设施", reason="增持"),
        _item("research", "AI算力基础设施", reason="强推"),
    ]
    results = engine.fuse(TD, items)
    # 3 × 0.55 = 1.65, but capped at 0.30 contribution
    assert results[0].evidence_score <= RESEARCH_MAX_CONTRIBUTION + 0.05  # ~0.30
    assert results[0].source_count == 1  # all same source


def test_why_strong_includes_research_count():
    """When research evidence is present, why_strong should show count."""
    from stock_processing_service.domain.services.leader_scoring import LeaderScoringEngine
    from stock_processing_service.domain.services.theme_strength import ThemeStrengthEngine
    from stock_processing_service.domain.services.recap_aggregation import RecapAggregationService

    fusion = EvidenceFusionEngine()
    leader_engine = LeaderScoringEngine(fusion)
    theme_engine = ThemeStrengthEngine()
    recap_service = RecapAggregationService()

    items = [
        _item("ths", "机器人", "002747", "埃斯顿", reason="人形机器人"),
        _item("research", "机器人", "002747", "埃斯顿", reason="中信买入"),
        _item("research", "机器人", "002747", "埃斯顿", reason="华泰增持"),
    ]
    board = {"002747": {"pct_chg": 10.0}}

    leaders = leader_engine.score(TD, items, board)
    themes = theme_engine.compute(TD, leaders)
    recap = recap_service.aggregate(TD, themes, leaders)

    robot_theme = recap.top_themes[0]
    has_research_reason = any("机构覆盖" in r for r in robot_theme["why_strong"])
    assert has_research_reason
    assert recap.market_summary["research_covered_stocks"] >= 1
    assert recap.market_summary["research_evidence_count"] >= 1  # fused per stock-theme


def test_empty_returns_empty():
    engine = EvidenceFusionEngine()
    results = engine.fuse(TD, [])
    assert len(results) == 0
