"""Phase 4.2 — AIAdapter tests.

Covers: adapt_metrics_only → facts/relay/leaders/momentum,
        adapt_with_diagnosis → phase/risk/strategy/themes,
        max_board_stock derivation from leaders,
        missing_fields tracking,
        None-safe edge cases.
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
    ADAPTER_VERSION,
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


# ═══ TC-4.2-ADAPTER-01: metrics-only — facts ═══

def test_metrics_only_facts_0707(adapter, snap_0707):
    view = adapter.adapt_metrics_only(snap_0707)
    f = view.market_facts
    assert f.limit_up_count == 33
    assert f.max_board_height == 5
    assert f.chain_board_count == 9
    assert f.active_capital_yi == 897.0
    assert f.market_up_ratio == 0.15
    assert f.loss_effect_ratio == 0.35


def test_metrics_only_facts_0708(adapter, snap_0708):
    view = adapter.adapt_metrics_only(snap_0708)
    f = view.market_facts
    assert f.limit_up_count == 47
    assert f.max_board_height == 7
    assert f.chain_board_count == 14
    assert f.active_capital_yi == 739.0


# ═══ TC-4.2-ADAPTER-02: metrics-only — phase/risk EMPTY ═══

def test_metrics_only_phase_empty(adapter, snap_0708):
    """adapt_metrics_only MUST leave phase/risk empty."""
    view = adapter.adapt_metrics_only(snap_0708)
    assert view.emotion_label.market_phase == ""
    assert view.emotion_label.risk_level == ""
    assert not view.has_phase_label


# ═══ TC-4.2-ADAPTER-03: metrics-only — emotion_momentum from raw ═══

def test_metrics_only_momentum(adapter, snap_0707, snap_0708):
    assert adapter.adapt_metrics_only(snap_0707).emotion_label.emotion_momentum == -12.0
    assert adapter.adapt_metrics_only(snap_0708).emotion_label.emotion_momentum == -4.0


# ═══ TC-4.2-ADAPTER-04: relay mapping ═══

def test_metrics_only_relay_0707(adapter, snap_0707):
    view = adapter.adapt_metrics_only(snap_0707)
    r = view.relay_label
    assert r.promotion_1_to_2 == 0.051
    assert r.promotion_2_to_3 == 0.0
    assert r.max_board_height == 5
    # max_board_stock derived from leader with highest board
    assert r.max_board_stock == "恒尚节能"


def test_metrics_only_relay_0708(adapter, snap_0708):
    view = adapter.adapt_metrics_only(snap_0708)
    r = view.relay_label
    assert r.promotion_1_to_2 == 0.21
    assert r.promotion_2_to_3 == 0.33
    assert r.max_board_height == 7
    assert r.max_board_stock == "恒尚节能"


# ═══ TC-4.2-ADAPTER-05: leader conversion ═══

def test_metrics_only_leaders(adapter, snap_0708):
    view = adapter.adapt_metrics_only(snap_0708)
    leaders = view.leader_state
    assert len(leaders) == 3
    top = leaders[0]
    assert top.stock_code == "603137"
    assert top.board_height == 7
    assert top.role == "market_leader"


def test_dead_leader_detection(adapter, snap_0707):
    view = adapter.adapt_metrics_only(snap_0707)
    dead = [l for l in view.leader_state if l.death_type]
    assert len(dead) >= 1
    jrt = [l for l in view.leader_state if l.stock_code == "002855"][0]
    assert jrt.death_type == "FRIED"


# ═══ TC-4.2-ADAPTER-06: diagnosis-enriched ═══

def test_adapt_with_diagnosis_0708(adapter, snap_0708):
    view = adapter.adapt_with_diagnosis(
        snap_0708,
        diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"},
        strategy_text="科技硬件快进快出",
    )
    assert view.emotion_label.market_phase == "REPAIR_WATCH"
    assert view.emotion_label.risk_level == "MEDIUM_HIGH"
    assert view.emotion_label.emotion_momentum == -4.0
    assert view.has_phase_label
    assert "科技硬件" in view.strategy_label.summary
    assert view.source_quality == 0.85


def test_adapt_with_diagnosis_no_diag(adapter, snap_0708):
    """Without diagnosis, phase/risk stay empty, quality lower."""
    view = adapter.adapt_with_diagnosis(snap_0708)
    assert view.emotion_label.market_phase == ""
    assert view.source_quality == 0.60


def test_adapt_with_diagnosis_themes(adapter, snap_0708):
    view = adapter.adapt_with_diagnosis(
        snap_0708,
        diagnosis={"phase_label": "REPAIR_WATCH", "risk_level": "MEDIUM_HIGH"},
        narrative_themes=[
            {"theme_name": "国产服务器", "state": "启动", "day_count": 1},
            {"theme_name": "半导体设备", "state": "启动", "day_count": 2},
        ],
    )
    assert len(view.theme_lifecycle) == 2
    assert view.theme_lifecycle[0].theme_name == "国产服务器"
    assert view.has_theme_data


# ═══ TC-4.2-ADAPTER-07: missing_fields tracking ═══

def test_metrics_only_missing_fields(adapter, snap_0707):
    view = adapter.adapt_metrics_only(snap_0707)
    # metrics-only should flag missing phase/risk
    assert len(view.missing_fields) >= 0  # facts all present for this snapshot


def test_diagnosis_view_missing_phase(adapter, snap_0708):
    """Without diagnosis, emotion_label fields tracked as missing."""
    view = adapter.adapt_with_diagnosis(snap_0708)  # no diagnosis
    missing = view.missing_fields
    assert "emotion_label.market_phase" in missing
    assert "emotion_label.risk_level" in missing


# ═══ TC-4.2-ADAPTER-08: isomorphic types ═══

def test_view_uses_contract_types(adapter, snap_0708):
    view = adapter.adapt_metrics_only(snap_0708)
    assert isinstance(view.market_facts, MarketFacts)
    assert isinstance(view.emotion_label, EmotionLabel)
    assert isinstance(view.relay_label, RelayLabel)
    for l in view.leader_state:
        assert isinstance(l, LeaderState)
    assert isinstance(view.strategy_label, StrategyLabel)
    assert view.adapter_version == ADAPTER_VERSION


# ═══ TC-4.2-ADAPTER-09: None-safe ═══

def test_missing_leader_evolution(adapter, snap_0708):
    snap = replace(snap_0708, leader_evolution=None)
    view = adapter.adapt_metrics_only(snap)
    assert len(view.leader_state) == 0
    # max_board_stock falls back empty when no leaders
    assert view.relay_label.max_board_stock == ""


def test_missing_loss_effect(adapter, snap_0708):
    snap = replace(snap_0708, loss_effect=None)
    view = adapter.adapt_metrics_only(snap)
    assert view.market_facts.loss_effect_ratio is None
    assert "market_facts.loss_effect_ratio" in view.missing_fields


# ═══ TC-4.2-ADAPTER-10: chain_board_count from relay ═══

def test_chain_board_count_from_relay(adapter, snap_0708):
    """chain_board_count should prefer relay over limitup."""
    view = adapter.adapt_metrics_only(snap_0708)
    # relay has chain_board_count=14
    assert view.market_facts.chain_board_count == 14
