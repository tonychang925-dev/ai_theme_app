from __future__ import annotations

from pathlib import Path

from stock_service.config import StockServiceConfig
from stock_service.services.tushare_dragon_tiger_snapshot_service import (
    TushareDragonTigerSnapshotService,
)


class _FakeDragonTigerAdapter:
    def __init__(self):
        self.top_list_calls = 0
        self.top_inst_calls = 0

    def fetch_top_list(self, trade_date: str, ts_codes=None):
        self.top_list_calls += 1
        return [{"trade_date": trade_date, "ts_code": "000001.SZ", "reason": "x"}]

    def fetch_top_inst(self, trade_date: str, ts_codes=None):
        self.top_inst_calls += 1
        return [{"trade_date": trade_date, "ts_code": "000001.SZ", "reason": "x", "exalter": "机构专用"}]


class _LateDragonTigerAdapter(_FakeDragonTigerAdapter):
    def fetch_top_list(self, trade_date: str, ts_codes=None):
        self.top_list_calls += 1
        if self.top_list_calls == 1:
            return []
        return [{"trade_date": trade_date, "ts_code": "000001.SZ", "reason": "x"}]


class _EmptyDragonTigerAdapter(_FakeDragonTigerAdapter):
    def fetch_top_list(self, trade_date: str, ts_codes=None):
        self.top_list_calls += 1
        return []


class _FakeIngestService:
    def __init__(self):
        self.calls = []

    def capture_snapshot(self, **kwargs):
        self.calls.append(kwargs)

        class _Result:
            snapshot_path = "/tmp/dragon_tiger_snapshot.json"

        return _Result()


def _config(tmp_path: Path) -> StockServiceConfig:
    return StockServiceConfig(
        raw_snapshot_root=tmp_path / "raw",
        report_snapshot_root=tmp_path / "report",
        tushare_token="token",
    )


def test_fetch_or_cache_top_list_hits_cache_on_second_call(tmp_path: Path):
    adapter = _FakeDragonTigerAdapter()
    service = TushareDragonTigerSnapshotService(_config(tmp_path), adapter=adapter)

    first = service.fetch_or_cache_top_list("2026-04-01")
    second = service.fetch_or_cache_top_list("2026-04-01")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert adapter.top_list_calls == 1
    assert second.row_count == 1


def test_fetch_or_cache_top_inst_hits_cache_on_second_call(tmp_path: Path):
    adapter = _FakeDragonTigerAdapter()
    service = TushareDragonTigerSnapshotService(_config(tmp_path), adapter=adapter)

    first = service.fetch_or_cache_top_inst("2026-04-01")
    second = service.fetch_or_cache_top_inst("2026-04-01")

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert adapter.top_inst_calls == 1
    assert second.row_count == 1


def test_fetch_or_cache_top_list_refreshes_zero_row_snapshot(tmp_path: Path):
    adapter = _LateDragonTigerAdapter()
    service = TushareDragonTigerSnapshotService(_config(tmp_path), adapter=adapter)

    first = service.fetch_or_cache_top_list("2026-04-01")
    second = service.fetch_or_cache_top_list("2026-04-01")

    assert first.row_count == 0
    assert first.cache_hit is False
    assert second.row_count == 1
    assert second.cache_hit is False
    assert adapter.top_list_calls == 2


def test_fetch_or_cache_top_list_empty_same_day_is_not_deferred(tmp_path: Path):
    adapter = _EmptyDragonTigerAdapter()
    ingest = _FakeIngestService()
    service = TushareDragonTigerSnapshotService(_config(tmp_path), adapter=adapter, ingest_service=ingest)

    result = service.fetch_or_cache_top_list("2026-06-04")

    assert result.row_count == 0
    assert result.cache_hit is False
    assert result.snapshot_path == "/tmp/dragon_tiger_snapshot.json"
    assert adapter.top_list_calls == 1
    assert len(ingest.calls) == 1
    assert ingest.calls[0]["dataset_name"] == "dragon_tiger_top_list"
    assert ingest.calls[0]["metadata"]["trade_date"] == "2026-06-04"
