from __future__ import annotations

from stock_processing_service.application.services.seat_money_snapshot_adapter import (
    SeatMoneySnapshotAdapter,
)


def test_seat_money_snapshot_adapter_outputs_none_contract_without_sources() -> None:
    summary = SeatMoneySnapshotAdapter().build(
        {
            "report_context": {
                "money_flow": [{"theme_name": "AI Chip", "role_label": "龙头"}],
                "theme_capital_flow": [{"theme_name": "AI Chip", "main_net_inflow_sum": 1}],
            }
        }
    )

    assert summary["institution_buy_rows"] == []
    assert summary["hot_money_buy_rows"] == []
    assert summary["diagnostics"]["source"] == "none"
    assert summary["diagnostics"]["dragon_tiger_row_count"] == 0
    assert summary["diagnostics"]["hot_money_activity_row_count"] == 0


def test_seat_money_snapshot_adapter_uses_only_explicit_seat_sources() -> None:
    summary = SeatMoneySnapshotAdapter().build(
        {
            "report_context": {
                "dragon_tiger": [
                    {
                        "stock_id": "002000.SZ",
                        "stock_name": "SampleA",
                        "theme_name": "AI Chip",
                        "net_amount": 12000000,
                        "institution_seat_count": 2,
                        "reason": "龙虎榜确认",
                    }
                ],
                "hot_money_activities": [
                    {
                        "hot_money_name": "测试席位",
                        "side": "买入",
                        "stock_id": "002000.SZ",
                        "stock_name": "SampleA",
                        "theme_name": "AI Chip",
                        "net_amount": 5000000,
                    }
                ],
                "money_flow": [
                    {"theme_name": "不应作为机构游资源", "role_label": "龙头", "main_net_inflow": 1}
                ],
                "theme_capital_flow": [
                    {"theme_name": "不应作为机构游资源", "main_net_inflow_sum": 1}
                ],
            }
        }
    )

    assert summary["diagnostics"]["source"] == "structured"
    assert summary["institution_buy_rows"][0]["stock_name"] == "SampleA"
    assert summary["institution_buy_rows"][0]["theme_name"] == "AI Chip"
    assert summary["hot_money_buy_rows"][0]["hot_money_name"] == "测试席位"
    assert summary["hot_money_buy_rows"][0]["buy_entries"][0]["stock_name"] == "SampleA"
    assert "不应作为机构游资源" not in str(summary)
