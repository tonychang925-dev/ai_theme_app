from __future__ import annotations

from stock_service.services.dragon_tiger_object_service import DragonTigerObjectService


def test_build_objects_aggregates_institution_summary_and_trace():
    service = DragonTigerObjectService()
    top_list_rows = service.normalize_top_list(
        [
            {
                "trade_date": "20260401",
                "ts_code": "300111.SZ",
                "name": "向例科技",
                "close": 21.5,
                "pct_change": 19.99,
                "turnover_rate": 12.3,
                "amount": 8.4e8,
                "l_sell": 1.0e8,
                "l_buy": 1.8e8,
                "l_amount": 2.8e8,
                "net_amount": 0.8e8,
                "net_rate": 9.52,
                "amount_rate": 33.33,
                "float_values": 55.5e8,
                "reason": "日涨幅偏离值达到7%的证券",
            }
        ]
    )
    top_inst_rows = service.normalize_top_inst(
        [
            {
                "trade_date": "20260401",
                "ts_code": "300111.SZ",
                "exalter": "机构专用",
                "side": "0",
                "buy": 56000000,
                "sell": 12000000,
                "net_buy": 44000000,
                "reason": "日涨幅偏离值达到7%的证券",
            },
            {
                "trade_date": "20260401",
                "ts_code": "300111.SZ",
                "exalter": "机构专用(二)",
                "side": "1",
                "buy": 18000000,
                "sell": 22000000,
                "net_buy": -4000000,
                "reason": "日涨幅偏离值达到7%的证券",
            },
        ]
    )

    result = service.build_objects(top_list_rows, top_inst_rows)

    assert len(result) == 1
    item = result[0]
    assert item.stock_id == "300111.SZ"
    assert item.institution_seat_count == 2
    assert item.institution_buy_amount == 74000000.0
    assert item.institution_sell_amount == 34000000.0
    assert item.institution_net_buy == 40000000.0
    assert item.source_trace["top_inst_row_count"] == 2
    assert item.source_trace_id
    assert len(item.seat_summary) == 2
    assert item.seat_summary[0]["seat_name"] == "机构专用"
    assert item.seat_summary[0]["side_label"] == "买入席位"
    assert item.seat_summary[1]["side_label"] == "卖出席位"


def test_normalize_top_list_skips_rows_without_reason_or_code():
    service = DragonTigerObjectService()

    result = service.normalize_top_list(
        [
            {"trade_date": "20260401", "ts_code": "", "reason": "x"},
            {"trade_date": "20260401", "ts_code": "000001.SZ", "reason": ""},
            {"trade_date": "20260401", "ts_code": "000001.SZ", "name": "平安银行", "reason": "日换手率达到20%的证券"},
        ]
    )

    assert len(result) == 1
    assert result[0].stock_id == "000001.SZ"
