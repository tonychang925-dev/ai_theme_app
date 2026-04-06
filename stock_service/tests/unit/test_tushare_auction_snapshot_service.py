from __future__ import annotations

from pathlib import Path

from stock_service.config import StockServiceConfig
from stock_service.services.tushare_auction_snapshot_service import TushareAuctionSnapshotService


class _FakeTushareAdapter:
    def __init__(self):
        self.calls = 0
        self.close_calls = 0

    def fetch_stk_auction(self, trade_date: str, ts_codes=None):
        self.calls += 1
        return [
            {
                "ts_code": "601872.SH",
                "trade_date": trade_date.replace("-", ""),
                "price": 19.12,
                "vol": 123456,
                "amount": 23456789,
            }
        ]

    def fetch_stk_auction_c(self, trade_date: str, ts_codes=None):
        self.close_calls += 1
        return [
            {
                "ts_code": "601872.SH",
                "trade_date": trade_date.replace("-", ""),
                "close": 19.22,
                "vol": 23456,
                "amount": 3456789,
                "vwap": 19.20,
            }
        ]


def _config(tmp_path: Path) -> StockServiceConfig:
    return StockServiceConfig(
        project_root=tmp_path,
        raw_snapshot_root=tmp_path / "raw_snapshots",
        tushare_token="test-token",
    )


def test_fetch_or_cache_stk_auction_writes_snapshot_on_first_fetch(tmp_path: Path):
    adapter = _FakeTushareAdapter()
    service = TushareAuctionSnapshotService(_config(tmp_path), adapter=adapter)

    result = service.fetch_or_cache_stk_auction("2026-04-03", ["601872.SH"])

    assert result.cache_hit is False
    assert result.row_count == 1
    assert result.snapshot_path
    assert adapter.calls == 1


def test_fetch_or_cache_stk_auction_uses_cache_on_second_call(tmp_path: Path):
    adapter = _FakeTushareAdapter()
    service = TushareAuctionSnapshotService(_config(tmp_path), adapter=adapter)

    first = service.fetch_or_cache_stk_auction("2026-04-03", ["601872.SH"])
    second = service.fetch_or_cache_stk_auction("2026-04-03", ["601872.SH"])

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.row_count == 1
    assert adapter.calls == 1


def test_fetch_or_cache_stk_auction_c_writes_snapshot_on_first_fetch(tmp_path: Path):
    adapter = _FakeTushareAdapter()
    service = TushareAuctionSnapshotService(_config(tmp_path), adapter=adapter)

    result = service.fetch_or_cache_stk_auction_c("2026-04-03", ["601872.SH"])

    assert result.cache_hit is False
    assert result.row_count == 1
    assert result.snapshot_path
    assert adapter.close_calls == 1


def test_fetch_or_cache_stk_auction_c_uses_cache_on_second_call(tmp_path: Path):
    adapter = _FakeTushareAdapter()
    service = TushareAuctionSnapshotService(_config(tmp_path), adapter=adapter)

    first = service.fetch_or_cache_stk_auction_c("2026-04-03", ["601872.SH"])
    second = service.fetch_or_cache_stk_auction_c("2026-04-03", ["601872.SH"])

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.row_count == 1
    assert adapter.close_calls == 1
