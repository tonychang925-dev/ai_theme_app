from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from stock_service.adapters.tushare_adapter import TushareAdapter
from stock_service.config import StockServiceConfig
from stock_service.raw_snapshot_store import RawSnapshotStore
from stock_service.services.source_ingest_service import SourceIngestService


@dataclass(frozen=True)
class TushareDailySnapshotResult:
    trade_date: str
    row_count: int
    cache_hit: bool
    snapshot_path: Optional[str]
    records: list[dict]


class TushareSnapshotService:
    def __init__(
        self,
        config: StockServiceConfig,
        adapter: TushareAdapter | None = None,
        ingest_service: SourceIngestService | None = None,
    ):
        self.config = config
        self.adapter = adapter or TushareAdapter(config.tushare_token)
        self.ingest_service = ingest_service or SourceIngestService(config)
        self.snapshot_store = RawSnapshotStore(config.raw_snapshot_root)

    def load_cached_daily_quotes(self, trade_date: str) -> TushareDailySnapshotResult | None:
        document = self.snapshot_store.load_json_snapshot(
            source_name="tushare",
            dataset_name="daily_quotes",
            trade_date=trade_date,
        )
        if not document:
            return None
        payload = document.get("payload")
        records = TushareAdapter.to_records(payload)
        return TushareDailySnapshotResult(
            trade_date=trade_date,
            row_count=len(records),
            cache_hit=True,
            snapshot_path=str(
                self.snapshot_store.find_latest_snapshot_path(
                    source_name="tushare",
                    dataset_name="daily_quotes",
                    trade_date=trade_date,
                )
            ),
            records=records,
        )

    def fetch_or_cache_daily_quotes(
        self,
        trade_date: str,
        ts_codes: Iterable[str] | None = None,
        *,
        force_refresh: bool = False,
    ) -> TushareDailySnapshotResult:
        if not force_refresh:
            cached = self.load_cached_daily_quotes(trade_date)
            if cached is not None:
                return cached

        frame = self.adapter.fetch_daily_quotes(trade_date, ts_codes)
        records = TushareAdapter.to_records(frame)
        batch_id = datetime.now().strftime("tushare_daily_%Y%m%d%H%M%S")
        ingest_result = self.ingest_service.capture_snapshot(
            source_name="tushare",
            dataset_name="daily_quotes",
            trade_date=trade_date,
            batch_id=batch_id,
            payload=records,
            owned_fields=[
                "stock_id",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "pre_close",
                "pct_chg",
                "volume",
                "amount",
            ],
            metadata={
                "trade_date": trade_date,
                "requested_codes": list(ts_codes or []),
            },
        )
        return TushareDailySnapshotResult(
            trade_date=trade_date,
            row_count=len(records),
            cache_hit=False,
            snapshot_path=ingest_result.snapshot_path,
            records=records,
        )
