from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from stock_service.adapters.tushare_adapter import TushareAdapter
from stock_service.config import StockServiceConfig
from stock_service.raw_snapshot_store import RawSnapshotStore
from stock_service.services.source_ingest_service import SourceIngestService


@dataclass(frozen=True)
class TushareAuctionSnapshotResult:
    trade_date: str
    row_count: int
    cache_hit: bool
    snapshot_path: Optional[str]
    records: list[dict]


class TushareAuctionSnapshotService:
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

    def load_cached_stk_auction(self, trade_date: str) -> TushareAuctionSnapshotResult | None:
        return self._load_cached_dataset("stk_auction", trade_date)

    def load_cached_stk_auction_c(self, trade_date: str) -> TushareAuctionSnapshotResult | None:
        return self._load_cached_dataset("stk_auction_c", trade_date)

    def _load_cached_dataset(self, dataset_name: str, trade_date: str) -> TushareAuctionSnapshotResult | None:
        document = self.snapshot_store.load_json_snapshot(
            source_name="tushare",
            dataset_name=dataset_name,
            trade_date=trade_date,
        )
        if not document:
            return None
        payload = document.get("payload")
        records = TushareAdapter.to_records(payload)
        path = self.snapshot_store.find_latest_snapshot_path(
            source_name="tushare",
            dataset_name=dataset_name,
            trade_date=trade_date,
        )
        return TushareAuctionSnapshotResult(
            trade_date=trade_date,
            row_count=len(records),
            cache_hit=True,
            snapshot_path=str(path) if path else None,
            records=records,
        )

    def fetch_or_cache_stk_auction(
        self,
        trade_date: str,
        ts_codes: Iterable[str] | None = None,
        *,
        force_refresh: bool = False,
    ) -> TushareAuctionSnapshotResult:
        return self._fetch_or_cache_dataset(
            "stk_auction",
            trade_date,
            ts_codes,
            force_refresh=force_refresh,
            fetcher=self.adapter.fetch_stk_auction,
            owned_fields=[
                "stock_id",
                "auction_open_price",
                "auction_open_pct",
                "auction_volume",
                "auction_amount",
            ],
        )

    def fetch_or_cache_stk_auction_c(
        self,
        trade_date: str,
        ts_codes: Iterable[str] | None = None,
        *,
        force_refresh: bool = False,
    ) -> TushareAuctionSnapshotResult:
        return self._fetch_or_cache_dataset(
            "stk_auction_c",
            trade_date,
            ts_codes,
            force_refresh=force_refresh,
            fetcher=self.adapter.fetch_stk_auction_c,
            owned_fields=[
                "stock_id",
                "tail_auction_close_price",
                "tail_auction_volume",
                "tail_auction_amount",
                "tail_auction_vwap",
            ],
        )

    def _fetch_or_cache_dataset(
        self,
        dataset_name: str,
        trade_date: str,
        ts_codes: Iterable[str] | None,
        *,
        force_refresh: bool,
        fetcher,
        owned_fields: list[str],
    ) -> TushareAuctionSnapshotResult:
        if not force_refresh:
            cached = self._load_cached_dataset(dataset_name, trade_date)
            if cached is not None:
                return cached

        frame = fetcher(trade_date, ts_codes)
        records = TushareAdapter.to_records(frame)
        batch_id = datetime.now().strftime(f"tushare_{dataset_name}_%Y%m%d%H%M%S")
        ingest_result = self.ingest_service.capture_snapshot(
            source_name="tushare",
            dataset_name=dataset_name,
            trade_date=trade_date,
            batch_id=batch_id,
            payload=records,
            owned_fields=owned_fields,
            metadata={
                "trade_date": trade_date,
                "requested_codes": list(ts_codes or []),
            },
        )
        return TushareAuctionSnapshotResult(
            trade_date=trade_date,
            row_count=len(records),
            cache_hit=False,
            snapshot_path=ingest_result.snapshot_path,
            records=records,
        )
