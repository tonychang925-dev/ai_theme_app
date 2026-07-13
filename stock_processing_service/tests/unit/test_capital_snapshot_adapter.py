from __future__ import annotations

from stock_processing_service.application.services.analyst_workbench.capital_snapshot_adapter import (
    CapitalSnapshotAdapter,
)


def test_capital_snapshot_adapter_maps_seat_money_summary() -> None:
    directions = CapitalSnapshotAdapter.directions_from_seat_money(
        {
            "institution_buy_rows": [
                {"theme_name": "国产算力", "stock_name": "SampleA", "net_buy": 50000000}
            ],
            "hot_money_buy_rows": [
                {
                    "hot_money_name": "测试席位",
                    "net_buy": 30000000,
                    "buy_entries": [
                        {"theme_name": "机器人", "stock_name": "SampleB", "net_amount": 30000000}
                    ],
                }
            ],
        }
    )

    assert directions["institution"] == [
        {
            "theme_name": "国产算力",
            "stock_name": "SampleA",
            "net_buy": 50000000,
            "source": "post_market_recap_snapshot.seat_money_summary.institution_buy_rows",
        }
    ]
    assert directions["hot_money"][0]["theme_name"] == "机器人"
    assert directions["hot_money"][0]["hot_money_name"] == "测试席位"
    assert directions["hot_money"][0]["source"] == (
        "post_market_recap_snapshot.seat_money_summary.hot_money_buy_rows"
    )


def test_capital_snapshot_adapter_keeps_empty_contract_when_no_seat_money() -> None:
    directions = CapitalSnapshotAdapter.directions_from_seat_money({})

    assert directions == {"institution": [], "hot_money": []}
