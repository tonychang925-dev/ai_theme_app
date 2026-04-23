from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from stock_service.services.weak_to_strong_auction_data_adapter import WeakToStrongAuctionDataAdapter


def test_calc_data_status_single_point_snapshot_is_partial():
    now_utc = datetime.now(timezone.utc)
    snapshot = {
        "created_at": now_utc - timedelta(minutes=5),
        "source_type": "p3.phase3.auction_snapshot",
        "shape_features": ["result_only_mode", "single_point_snapshot"],
        "source_trace": {"record_mode": "single_point"},
    }

    status, latency_ms = WeakToStrongAuctionDataAdapter._calc_data_status(snapshot, now_utc, date.today())

    assert status == "partial"
    assert latency_ms >= 0


def test_calc_data_status_today_outside_auction_window_is_not_delayed():
    now_utc = datetime.now(timezone.utc)
    snapshot = {
        "created_at": now_utc - timedelta(minutes=6),
        "source_type": "p3.phase3.auction_snapshot",
        "shape_features": [],
        "source_trace": {},
    }

    status, latency_ms = WeakToStrongAuctionDataAdapter._calc_data_status(snapshot, now_utc, date.today())

    assert status in {"ok", "partial"}
    assert status != "delayed"
    assert latency_ms >= 0
