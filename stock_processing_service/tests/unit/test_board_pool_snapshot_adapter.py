"""PR4.2.28b BoardPoolSnapshot amount completeness contract."""

from __future__ import annotations

from datetime import date

from stock_processing_service.application.services.market_metrics.board_pool_snapshot import (
    BoardPoolSnapshotAdapter,
)


class FakeConn:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.query = ""
        self.args = ()

    async def fetch(self, query: str, *args):
        self.query = query
        self.args = args
        return self.rows


async def test_board_pool_snapshot_marks_zt_amount_ok_and_zb_missing() -> None:
    """TC-ID: PR4.2.28b-board-pool-snapshot-20260709."""
    conn = FakeConn(
        [
            {"pool_type": "ZT", "stock_code": "603986", "amount": 38185017344.0, "turnover": 12.3, "raw_json": {}},
            {"pool_type": "ZT", "stock_code": "002384", "amount": 27786395392.0, "turnover": 8.1, "raw_json": {}},
            {"pool_type": "ZB", "stock_code": "605006", "amount": 0.0, "turnover": 10.38, "raw_json": {}},
            {"pool_type": "YZT", "stock_code": "600000", "amount": 0.0, "turnover": 0.0, "raw_json": {}},
        ]
    )

    snapshot = await BoardPoolSnapshotAdapter().load(conn, date(2026, 7, 9))

    assert "eastmoney_board_pool_daily" in conn.query
    assert snapshot.source == "eastmoney_board_pool_daily"
    assert snapshot.unit == "yi"
    assert snapshot.zt.rows == 2
    assert snapshot.zt.amount_yi == 659.71
    assert snapshot.zt.amount_source == "eastmoney_board_pool_daily.amount"
    assert snapshot.zt.quality == "OK"
    assert snapshot.zb.rows == 1
    assert snapshot.zb.amount_yi is None
    assert snapshot.zb.amount_source is None
    assert snapshot.zb.quality == "MISSING"
    assert snapshot.yzt.quality == "MISSING"
    assert snapshot.diagnostics["multiplier_used"] is False
    assert snapshot.diagnostics["hardcoded_analyst_truth"] is False
    assert "board_pool.zb.amount_yi" in snapshot.diagnostics["missing"]


async def test_board_pool_snapshot_does_not_turn_zb_turnover_rate_into_amount() -> None:
    """TC-ID: PR4.2.28b-zb-turnover-rate-not-amount."""
    conn = FakeConn(
        [
            {"pool_type": "ZB", "stock_code": "605006", "amount": None, "turnover": 99.99, "raw_json": {}},
        ]
    )

    snapshot = await BoardPoolSnapshotAdapter().load(conn, date(2026, 7, 9))

    assert snapshot.zb.rows == 1
    assert snapshot.zb.amount_yi is None
    assert snapshot.zb.quality == "MISSING"
    assert "board_pool.zb.amount_yi" in snapshot.diagnostics["missing"]


async def test_board_pool_snapshot_missing_pool_reports_rows_and_amount() -> None:
    """TC-ID: PR4.2.28b-missing-pool-diagnostics."""
    snapshot = await BoardPoolSnapshotAdapter().load(FakeConn([]), date(2026, 7, 9))

    assert snapshot.zt.rows == 0
    assert snapshot.zt.amount_yi is None
    assert snapshot.zt.quality == "MISSING"
    assert "board_pool.zt.rows" in snapshot.diagnostics["missing"]
    assert "board_pool.zt.amount_yi" in snapshot.diagnostics["missing"]
