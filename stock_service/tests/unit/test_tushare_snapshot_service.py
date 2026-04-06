from __future__ import annotations

from pathlib import Path

from stock_service.config import StockServiceConfig
from stock_service.services.tushare_snapshot_service import TushareSnapshotService


class _FakeTushareAdapter:
    def __init__(self):
        self.calls = 0

    def fetch_daily_quotes(self, trade_date: str, ts_codes=None):
        self.calls += 1
        return [
            {
                "ts_code": "601872.SH",
                "close": 18.0,
                "pct_chg": 10.02,
                "amount": 3523412682,
            }
        ]


def _config(tmp_path: Path) -> StockServiceConfig:
    return StockServiceConfig(
        project_root=tmp_path,
        raw_snapshot_root=tmp_path / "raw_snapshots",
        tushare_token="test-token",
    )


def test_fetch_or_cache_daily_quotes_writes_snapshot_on_first_fetch(tmp_path: Path):
    adapter = _FakeTushareAdapter()
    service = TushareSnapshotService(_config(tmp_path), adapter=adapter)

    result = service.fetch_or_cache_daily_quotes("2026-04-01", ["601872.SH"])

    assert result.cache_hit is False
    assert result.row_count == 1
    assert result.snapshot_path
    assert adapter.calls == 1


def test_fetch_or_cache_daily_quotes_uses_cache_on_second_call(tmp_path: Path):
    adapter = _FakeTushareAdapter()
    service = TushareSnapshotService(_config(tmp_path), adapter=adapter)

    first = service.fetch_or_cache_daily_quotes("2026-04-01", ["601872.SH"])
    second = service.fetch_or_cache_daily_quotes("2026-04-01", ["601872.SH"])

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.row_count == 1
    assert adapter.calls == 1
