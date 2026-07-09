"""Phase 4.2 — AIAdapter tests.

Covers: snapshot → AIDiagnosisReferenceView conversion,
        isomorphic structure verification, narrative enrichment,
        edge cases (None/missing fields), leader role derivation.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from stock_processing_service.application.services.analyst_reference.contracts import (
    EmotionLabel,
    LeaderState,
    MarketFacts,
    RelayLabel,
    StrategyLabel,
    ThemeLifecycleEntry,
)
from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
    AIAdapter,
    AIDiagnosisReferenceView,
)
from stock_processing_service.application.services.market_metrics.contracts import (
    ActiveCapitalMetrics,
    EmotionMomentumMetrics,
    LeaderEvolutionMetrics,
    LeaderSnapshot,
    LimitUpMetrics,
    LossEffectMetrics,
    MarketBreadthMetrics,
    MarketMetricsSnapshot,
    MetricSource,
    RelayEcologyMetrics,
)


# ═══ Builders ═══

def _src(label: str = "mock") -> MetricSource:
    return MetricSource(source_type=label)


def _build_mock_snapshot_0707() -> MarketMetricsSnapshot:
    """Build a mock MarketMetricsSnapshot matching 7/7 PANIC day AI output."""
    return MarketMetricsSnapshot(
        trade_date=date(2026, 7, 7),
        breadth=MarketBreadthMetrics(
            up_count=633, down_count=4482, limit_up_count=33, limit_down_count=30,
            up_ratio=0.15, turnover_yi=897.0, source=_src("breadth"),
        ),
        limitup=LimitUpMetrics(
            total_count=33, sealed_count=28, fried_board_count=5,
            chain_board_count=9, current_board_height=5, historical_streak_height=5,
            max_board_height=5, max_turnover_board_height=5,
            first_board_count=24, first_board_success_rate=0.727,
            sealed_board_ratio=0.848, high_board_count=3,
            source=_src("limitup"),
        ),
        relay=RelayEcologyMetrics(
            promotion_1_to_2=0.051, promotion_2_to_3=0.0,
            promotion_3_to_4=0.0, chain_board_count=9,
            max_board_height=5, max_turnover_board_height=5,
            yesterday_limitup_count=48, today_continue_count=3,
            continue_ratio=0.0625, yesterday_big_loss_count=8,
            source=_src("relay"),
        ),
        capital=ActiveCapitalMetrics(
            total_turnover_yi=897.0, active_limitup_amount_yi=897.0,
            active_ratio=0.12, source=_src("capital"),
        ),
        emotion_momentum=EmotionMomentumMetrics(
            first_board_red_ratio=0.4, first_board_big_loss_ratio=0.15,
            chain_board_red_ratio=0.3, chain_board_ratio=0.27,
            chain_board_big_loss_ratio=0.1, yesterday_chain_not_limit_red_ratio=0.2,
            momentum_raw=-12.0, momentum_normalized=-66.7,
            source=_src("emotion"),
        ),
        loss_effect=LossEffectMetrics(
            limit_down_count=30, limit_down_ratio=0.005,
            big_loss_count=12, damage_ratio=0.35, loss_effect_score=78.0,
            loss_effect_label="SEVERE",
            source=_src("loss"),
        ),
        leader_evolution=LeaderEvolutionMetrics(
            trade_date=date(2026, 7, 7),
            leaders=(
                LeaderSnapshot(
                    stock_code="603137", stock_name="恒尚节能",
                    board_height=5, status="NORMAL_CONTINUE",
                    relative_height=1.0, strength_score=0.85,
                    death_type="", theme_hint="算力/半导体",
                ),
                LeaderSnapshot(
                    stock_code="002855", stock_name="捷荣技术",
                    board_height=3, status="WEAKEN_UNEXPECTED",
                    relative_height=0.6, strength_score=0.5,
                    death_type="FRIED", theme_hint="半导体设备",
                ),
            ),
            leader_health_score=45.0, leader_health_label="WEAK",
            leader_break_alert=True,
            source=_src("leader"),
        ),
    )


def _build_mock_snapshot_0708() -> MarketMetricsSnapshot:
    """Build a mock MarketMetricsSnapshot matching 7/8 REPAIR_WATCH day AI output."""
    return MarketMetricsSnapshot(
        trade_date=date(2026, 7, 8),
        breadth=MarketBreadthMetrics(
            up_count=1800, down_count=2700, limit_up_count=47, limit_down_count=41,
            up_ratio=0.35, turnover_yi=739.0, source=_src("breadth"),
        ),
        limitup=LimitUpMetrics(
            total_count=47, sealed_count=33, fried_board_count=14,
            chain_board_count=14, current_board_height=7, historical_streak_height=7,
            max_board_height=7, max_turnover_board_height=7,
            first_board_count=33, first_board_success_rate=0.702,
            sealed_board_ratio=0.702, high_board_count=5,
            source=_src("limitup"),
        ),
        relay=RelayEcologyMetrics(
            promotion_1_to_2=0.21, promotion_2_to_3=0.33,
            promotion_3_to_4=0.0, chain_board_count=14,
            max_board_height=7, max_turnover_board_height=7,
            yesterday_limitup_count=33, today_continue_count=7,
            continue_ratio=0.212, yesterday_big_loss_count=5,
            source=_src("relay"),
        ),
        capital=ActiveCapitalMetrics(
            total_turnover_yi=739.0, active_limitup_amount_yi=739.0,
            active_ratio=0.10, source=_src("capital"),
        ),
        emotion_momentum=EmotionMomentumMetrics(
            first_board_red_ratio=0.55, first_board_big_loss_ratio=0.08,
            chain_board_red_ratio=0.45, chain_board_ratio=0.30,
            chain_board_big_loss_ratio=0.05, yesterday_chain_not_limit_red_ratio=0.35,
            momentum_raw=-4.0, momentum_normalized=-22.2,
            source=_src("emotion"),
        ),
        loss_effect=LossEffectMetrics(
            limit_down_count=41, limit_down_ratio=0.007,
            big_loss_count=8, damage_ratio=0.18, loss_effect_score=45.0,
            loss_effect_label="MODERATE",
            source=_src("loss"),
        ),
        leader_evolution=LeaderEvolutionMetrics(
            trade_date=date(2026, 7, 8),
            leaders=(
                LeaderSnapshot(
                    stock_code="603137", stock_name="恒尚节能",
                    board_height=7, status="SUPER_CONTINUE",
                    relative_height=1.0, strength_score=0.92,
                    death_type="", theme_hint="算力/半导体",
                ),
                LeaderSnapshot(
                    stock_code="002855", stock_name="捷荣技术",
                    board_height=3, status="NORMAL_CONTINUE",
                    relative_height=0.43, strength_score=0.6,
                    death_type="", theme_hint="半导体设备",
                ),
                LeaderSnapshot(
                    stock_code="600105", stock_name="永鼎股份",
                    board_height=2, status="NEW",
                    relative_height=0.29, strength_score=0.4,
                    death_type="", theme_hint="通信/6G",
                ),
            ),
            leader_health_score=65.0, leader_health_label="NORMAL",
            leader_break_alert=False,
            source=_src("leader"),
        ),
    )


@pytest.fixture
def adapter():
    return AIAdapter()


@pytest.fixture
def snap_0707():
    return _build_mock_snapshot_0707()


@pytest.fixture
def snap_0708():
    return _build_mock_snapshot_0708()


# ═══ TC-4.2-ADAPTER-01: Core facts conversion ═══

def test_adapt_facts_0707(adapter, snap_0707):
    view = adapter.adapt(snap_0707, diagnosis={"phase_label": "PANIC", "risk_level": "HIGH"})
    f = view.market_facts
    assert f.limit_up_count == 33
    assert f.max_board_height == 5
    assert f.active_capital_yi == 897.0
    assert f.market_up_ratio == 0.15
    assert f.loss_effect_ratio == 0.35


def test_adapt_facts_0708(adapter, snap_0708):
    view = adapter.adapt(snap_0708, diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"})
    f = view.market_facts
    assert f.limit_up_count == 47
    assert f.max_board_height == 7
    assert f.active_capital_yi == 739.0


# ═══ TC-4.2-ADAPTER-02: Emotion conversion ═══

def test_adapt_emotion_0707(adapter, snap_0707):
    view = adapter.adapt(snap_0707, diagnosis={"phase_label": "PANIC", "risk_level": "HIGH"})
    e = view.emotion_label
    assert e.market_phase == "PANIC"
    assert e.risk_level == "HIGH"
    assert e.emotion_momentum == -12.0


def test_adapt_emotion_0708(adapter, snap_0708):
    view = adapter.adapt(snap_0708, diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"})
    e = view.emotion_label
    assert e.market_phase == "REPAIR_WATCH"
    assert e.risk_level == "MEDIUM_HIGH"
    assert e.emotion_momentum == -4.0


# ═══ TC-4.2-ADAPTER-03: Relay conversion ═══

def test_adapt_relay_0707(adapter, snap_0707):
    view = adapter.adapt(snap_0707, diagnosis={"phase_label": "PANIC", "risk_level": "HIGH"})
    r = view.relay_label
    assert r.promotion_1_to_2 == 0.051
    assert r.promotion_2_to_3 == 0.0
    assert r.max_board_height == 5


def test_adapt_relay_0708(adapter, snap_0708):
    view = adapter.adapt(snap_0708, diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"})
    r = view.relay_label
    assert r.promotion_1_to_2 == 0.21
    assert r.promotion_2_to_3 == 0.33
    assert r.max_board_height == 7


# ═══ TC-4.2-ADAPTER-04: Leader conversion ═══

def test_adapt_leaders_0707(adapter, snap_0707):
    view = adapter.adapt(snap_0707, diagnosis={"phase_label": "PANIC", "risk_level": "HIGH"})
    leaders = view.leader_state
    assert len(leaders) == 2

    top = leaders[0]
    assert top.stock_code == "603137"
    assert top.stock_name == "恒尚节能"
    assert top.board_height == 5
    assert top.role in ("market_leader", "theme_leader", "")
    assert top.theme == "算力/半导体"


def test_adapt_leaders_0708(adapter, snap_0708):
    view = adapter.adapt(snap_0708, diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"})
    leaders = view.leader_state
    assert len(leaders) == 3

    # Market leader should be 603137 at 7 boards
    top = leaders[0]
    assert top.stock_code == "603137"
    assert top.board_height == 7
    assert top.role == "market_leader"


# ═══ TC-4.2-ADAPTER-05: Dead leader detection ═══

def test_dead_leader_detection(adapter, snap_0707):
    view = adapter.adapt(snap_0707, diagnosis={"phase_label": "PANIC", "risk_level": "HIGH"})
    # 捷荣技术 should have death_type=FRIED and role=weakened_leader
    dead = [l for l in view.leader_state if l.death_type]
    assert len(dead) >= 1
    jrt = [l for l in view.leader_state if l.stock_code == "002855"][0]
    assert jrt.death_type == "FRIED"


# ═══ TC-4.2-ADAPTER-06: Isomorphic type verification ═══

def test_view_uses_contract_types(adapter, snap_0708):
    """AIDiagnosisReferenceView uses the same sub-object types as AnalystReferenceRecord."""
    view = adapter.adapt(snap_0708, diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"})

    assert isinstance(view.market_facts, MarketFacts)
    assert isinstance(view.emotion_label, EmotionLabel)
    assert isinstance(view.relay_label, RelayLabel)
    for l in view.leader_state:
        assert isinstance(l, LeaderState)
    assert isinstance(view.strategy_label, StrategyLabel)


# ═══ TC-4.2-ADAPTER-07: None-safe (missing leader_evolution) ═══

def test_missing_leader_evolution(adapter, snap_0708):
    snap = replace(snap_0708, leader_evolution=None)
    view = adapter.adapt(snap, diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"})
    assert len(view.leader_state) == 0


# ═══ TC-4.2-ADAPTER-08: Narrative enrichment ═══

def test_adapt_with_narrative_themes(adapter, snap_0708):
    narrative_themes = [
        {"theme_name": "国产服务器", "state": "启动", "day_count": 1},
        {"theme_name": "半导体设备", "state": "启动", "day_count": 2},
    ]
    view = adapter.adapt_with_narrative(
        snap_0708, narrative_themes=narrative_themes,
        strategy_text="科技硬件快进快出",
    )
    assert len(view.theme_lifecycle) == 2
    assert view.theme_lifecycle[0].theme_name == "国产服务器"
    assert view.has_strategy_data
    assert "科技硬件" in view.strategy_label.summary


def test_adapt_without_narrative(adapter, snap_0708):
    view = adapter.adapt(snap_0708, diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"})
    # Without narrative, themes/strategy/attribution are empty
    assert len(view.theme_lifecycle) == 0
    assert not view.has_strategy_data
    assert not view.has_theme_data


# ═══ TC-4.2-ADAPTER-09: Missing loss_effect ═══

def test_missing_loss_effect(adapter, snap_0708):
    snap = replace(snap_0708, loss_effect=None)
    view = adapter.adapt(snap, diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"})
    # loss_effect_ratio should be None, not crash
    assert view.market_facts.loss_effect_ratio is None
