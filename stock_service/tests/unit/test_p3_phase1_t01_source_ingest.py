from __future__ import annotations

import json
from pathlib import Path

import pytest

from stock_service.config import StockServiceConfig
from stock_service.services.source_ingest_service import SourceIngestService
from stock_service.source_contract import DEFAULT_SOURCE_OWNERSHIP
from stock_service.adapters.tushare_adapter import TushareAdapter


class FakeFrame:
    def __init__(self, rows):
        self._rows = rows

    def to_dict(self, orient="records"):
        assert orient == "records"
        return self._rows


def make_config(tmp_path: Path) -> StockServiceConfig:
    return StockServiceConfig(
        project_root=tmp_path,
        raw_snapshot_root=tmp_path / "_raw_stock_sources",
    )


def test_source_ownership_registry_accepts_owned_fields():
    DEFAULT_SOURCE_OWNERSHIP.validate_payload(
        ["trade_date", "stock_id", "close_price", "pct_chg"],
        "tushare",
    )
    DEFAULT_SOURCE_OWNERSHIP.validate_payload(
        ["subject_key", "theme_event_summary", "theme_stock_pool"],
        "jyhf",
    )


def test_source_ownership_registry_rejects_conflicts():
    with pytest.raises(ValueError):
        DEFAULT_SOURCE_OWNERSHIP.validate_payload(["theme_stock_pool"], "tushare")

    with pytest.raises(ValueError):
        DEFAULT_SOURCE_OWNERSHIP.validate_payload(["close_price"], "jyhf")


def test_raw_snapshot_is_written_before_ingest(tmp_path: Path):
    service = SourceIngestService(make_config(tmp_path))
    result = service.capture_snapshot(
        source_name="tushare",
        dataset_name="daily_quotes",
        trade_date="2026-04-02",
        batch_id="batch_001",
        payload=[{"ts_code": "000001.SZ", "close": 12.3}],
        owned_fields=["trade_date", "stock_id", "close_price"],
        metadata={"note": "unit-test"},
    )

    snapshot_path = Path(result.snapshot_path)
    assert snapshot_path.exists()
    document = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert document["source_name"] == "tushare"
    assert document["dataset_name"] == "daily_quotes"
    assert document["trade_date"] == "2026-04-02"
    assert document["metadata"]["note"] == "unit-test"
    assert document["payload"][0]["ts_code"] == "000001.SZ"
    assert result.row_count == 1


def test_tushare_adapter_to_records_uses_dataframe_contract():
    rows = [{"ts_code": "000001.SZ", "trade_date": "20260402", "close": 12.3}]
    frame = FakeFrame(rows)
    assert TushareAdapter.to_records(frame) == rows
