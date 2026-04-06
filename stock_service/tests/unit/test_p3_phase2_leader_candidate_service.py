from __future__ import annotations

from stock_service.services.leader_candidate_service import (
    LeaderCandidateService,
    ThemeLeaderInput,
)


def _row(**overrides):
    base = dict(
        trade_date="2026-04-01",
        subject_key="9064088",
        theme_name="商业航天",
        stock_id="600000.SH",
        stock_name="样本股",
        rank_order=1,
        pct_chg=10.0,
        is_leader=True,
        is_limit_up=True,
        turnover_rate=18.0,
        volume_ratio=6.0,
        main_net_inflow=2.5e8,
        is_new_stock=False,
        close_price=18.0,
    )
    base.update(overrides)
    return ThemeLeaderInput(**base)


def test_build_theme_candidates_outputs_top_roles_in_order():
    service = LeaderCandidateService()
    rows = [
        _row(stock_id="600001.SH", stock_name="龙头股", rank_order=1, pct_chg=10.0, is_leader=True, is_limit_up=True, turnover_rate=20.0, volume_ratio=7.0),
        _row(stock_id="600002.SH", stock_name="龙二股", rank_order=2, pct_chg=10.0, is_leader=False, is_limit_up=True, turnover_rate=15.0, volume_ratio=5.0),
        _row(stock_id="600003.SH", stock_name="补涨股", rank_order=3, pct_chg=8.0, is_limit_up=False, turnover_rate=10.0, volume_ratio=4.0),
        _row(stock_id="600004.SH", stock_name="杂毛股", rank_order=12, pct_chg=1.0, is_limit_up=False, turnover_rate=2.0, volume_ratio=1.0, main_net_inflow=0.0),
        _row(stock_id="600005.SH", stock_name="中位股", rank_order=5, pct_chg=5.0, is_limit_up=False, turnover_rate=8.0, volume_ratio=2.5),
    ]

    result = service.build_theme_candidates(rows)

    assert [x.candidate_rank for x in result] == [1, 2, 3, 4]
    assert result[0].role_label == "龙头"
    assert result[1].role_label in {"龙二", "卡位"}
    assert result[3].role_label == "淘汰"


def test_build_theme_candidates_keeps_fact_fields():
    service = LeaderCandidateService()
    result = service.build_theme_candidates([_row(is_new_stock=True, turnover_rate=12.3, volume_ratio=3.5, main_net_inflow=1.2e8)])[0]

    assert result.turnover_rate == 12.3
    assert result.volume_ratio == 3.5
    assert result.is_new_stock is True
    assert result.limit_up_type == "leader_limit_up"
    assert result.main_net_inflow == 1.2e8


def test_build_theme_candidates_includes_kline_position_and_pattern_signal():
    service = LeaderCandidateService()
    result = service.build_theme_candidates(
        [
            _row(
                position_label="低位启动",
                trend_strength_score=80.0,
                pattern_labels=("放量突破", "高量不破"),
            )
        ]
    )[0]

    assert result.structure_score >= 60
    assert any("K线位置 低位启动" in item for item in result.evidence)
    assert any("K线形态 放量突破/高量不破" in item for item in result.evidence)
