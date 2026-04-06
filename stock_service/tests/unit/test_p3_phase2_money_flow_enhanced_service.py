from __future__ import annotations

from stock_service.services.money_flow_enhanced_service import (
    MoneyFlowEnhancedService,
    MoneyFlowInput,
)


def _row(**overrides):
    base = dict(
        trade_date="2026-04-01",
        subject_key="9013933",
        theme_name="共封装光学CPO",
        stock_id="688025.SH",
        stock_name="杰普特",
        role_label="龙头",
        candidate_rank=1,
        composite_score=61.14,
        turnover_rate=18.0,
        volume_ratio=6.0,
        main_net_inflow=1.5e8,
        is_limit_up=True,
        dragon_tiger_net_amount=0.8e8,
        institution_seat_count=10,
    )
    base.update(overrides)
    return MoneyFlowInput(**base)


def test_build_item_outputs_high_tier_for_strong_capital_resonance():
    service = MoneyFlowEnhancedService()

    item = service.build_item(_row(position_label="低位启动", pattern_labels=("放量突破",)))

    assert item.money_flow_tier == "HIGH"
    assert item.role_enhanced == "龙头/资金共振"
    assert any("资金分层 HIGH" in line for line in item.explanation)
    assert any("K线位置 低位启动" in line for line in item.explanation)
    assert any("K线形态 放量突破" in line for line in item.explanation)
    assert "dragon_tiger_object" in item.sources


def test_build_item_keeps_leader_semantics_when_not_high():
    service = MoneyFlowEnhancedService()

    item = service.build_item(
        _row(
            main_net_inflow=10000000,
            dragon_tiger_net_amount=0,
            institution_seat_count=0,
            volume_ratio=1.2,
            turnover_rate=5.0,
        )
    )

    assert item.role_label == "龙头"
    assert item.role_enhanced == "龙头观察"


def test_build_item_outputs_follow_for_weak_candidate():
    service = MoneyFlowEnhancedService()

    item = service.build_item(
        _row(
            stock_id="600000.SH",
            stock_name="跟风股",
            role_label="淘汰",
            candidate_rank=4,
            composite_score=20.0,
            turnover_rate=1.5,
            volume_ratio=0.8,
            main_net_inflow=0.0,
            is_limit_up=False,
            dragon_tiger_net_amount=0.0,
            institution_seat_count=0,
        )
    )

    assert item.money_flow_tier == "LOW"
    assert item.role_enhanced == "跟风"
