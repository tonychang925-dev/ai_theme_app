from __future__ import annotations

from stock_service.services.auction_signal_service import AuctionCandidateInput
from stock_service.services.auction_snapshot_builder_service import AuctionSnapshotBuilderService


def _candidate() -> AuctionCandidateInput:
    return AuctionCandidateInput(
        trade_date="2026-04-03",
        stock_id="601872.SH",
        stock_name="招商轮船",
        subject_key="9018216",
        theme_name="石油",
        role_label="龙头",
        is_main_theme=True,
        action_bias="主做",
        is_reversal_watch=False,
    )


def test_parse_tushare_auction_record_normalizes_core_fields():
    service = AuctionSnapshotBuilderService()
    parsed = service.parse_tushare_auction_record(
        {
            "ts_code": "601872.SH",
            "price": 19.12,
            "vol": 123456,
            "amount": 23456789,
            "pre_close": 18.00,
        }
    )

    assert parsed.stock_id == "601872.SH"
    assert parsed.auction_open_price == 19.12
    assert parsed.auction_volume == 123456
    assert parsed.auction_amount == 23456789
    assert parsed.pre_close == 18.00


def test_build_single_point_snapshot_marks_single_point_trace_and_proxy():
    service = AuctionSnapshotBuilderService()
    parsed = service.parse_tushare_auction_record(
        {
            "ts_code": "601872.SH",
            "price": 19.12,
            "vol": 123456,
            "amount": 23456789,
            "pre_close": 18.00,
        }
    )
    snapshot = service.build_single_point_snapshot(
        _candidate(),
        parsed,
        prev_day_close=18.00,
        prev_day_max_intraday_amount_proxy=40000000.0,
    )

    assert snapshot.stock_id == "601872.SH"
    assert snapshot.source_trace["record_mode"] == "single_point"
    assert snapshot.source_trace["proxy_method"] == "subject_stock_daily_snapshot.amount * proxy_ratio"
    assert "result_only_mode" in snapshot.shape_features
    assert "single_point_snapshot" in snapshot.shape_features
    assert snapshot.carry_ratio > 0


def test_build_timeline_enhanced_snapshot_uses_last_minute_delta():
    service = AuctionSnapshotBuilderService()
    parsed = service.parse_tushare_auction_record(
        {
            "ts_code": "601872.SH",
            "price": 19.12,
            "vol": 123456,
            "amount": 23456789,
            "pre_close": 18.00,
        }
    )
    points = service.parse_timeline_points(
        [
            {"ts": "09:23:30", "price": 18.80, "amount": 12000000},
            {"ts": "09:24:00", "price": 18.95, "amount": 15000000},
            {"ts": "09:24:30", "price": 19.05, "amount": 19000000},
            {"ts": "09:25:00", "price": 19.12, "amount": 23456789},
        ]
    )
    snapshot = service.build_timeline_enhanced_snapshot(
        _candidate(),
        parsed,
        timeline_points=points,
        prev_day_close=18.00,
        prev_day_max_intraday_amount_proxy=40000000.0,
    )

    assert snapshot.source_trace["record_mode"] == "timeline_enhanced"
    assert snapshot.source_trace["timeline_point_count"] == 4
    assert "timeline_enhanced" in snapshot.shape_features
    assert snapshot.last_minute_amount == 8456789
