from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from stock_service.adapters.tushare_adapter import TushareAdapter
from stock_service.config import StockServiceConfig
from stock_service.raw_snapshot_store import RawSnapshotStore
from stock_service.services.source_ingest_service import SourceIngestService


@dataclass(frozen=True)
class TushareDragonTigerSnapshotResult:
    trade_date: str
    dataset_name: str
    row_count: int
    cache_hit: bool
    snapshot_path: Optional[str]
    records: list[dict]


class TushareDragonTigerSnapshotService:
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

    def load_cached_top_list(self, trade_date: str) -> TushareDragonTigerSnapshotResult | None:
        return self._load_cached(dataset_name="dragon_tiger_top_list", trade_date=trade_date)

    def load_cached_top_inst(self, trade_date: str) -> TushareDragonTigerSnapshotResult | None:
        return self._load_cached(dataset_name="dragon_tiger_top_inst", trade_date=trade_date)

    def fetch_or_cache_top_list(
        self,
        trade_date: str,
        ts_codes: Iterable[str] | None = None,
        *,
        force_refresh: bool = False,
    ) -> TushareDragonTigerSnapshotResult:
        return self._fetch_or_cache(
            dataset_name="dragon_tiger_top_list",
            trade_date=trade_date,
            ts_codes=ts_codes,
            force_refresh=force_refresh,
        )

    def fetch_or_cache_top_inst(
        self,
        trade_date: str,
        ts_codes: Iterable[str] | None = None,
        *,
        force_refresh: bool = False,
    ) -> TushareDragonTigerSnapshotResult:
        return self._fetch_or_cache(
            dataset_name="dragon_tiger_top_inst",
            trade_date=trade_date,
            ts_codes=ts_codes,
            force_refresh=force_refresh,
        )

    def _load_cached(self, *, dataset_name: str, trade_date: str) -> TushareDragonTigerSnapshotResult | None:
        document = self.snapshot_store.load_json_snapshot(
            source_name="tushare",
            dataset_name=dataset_name,
            trade_date=trade_date,
        )
        if not document:
            return None
        payload = document.get("payload")
        records = TushareAdapter.to_records(payload)
        latest = self.snapshot_store.find_latest_snapshot_path(
            source_name="tushare",
            dataset_name=dataset_name,
            trade_date=trade_date,
        )
        return TushareDragonTigerSnapshotResult(
            trade_date=trade_date,
            dataset_name=dataset_name,
            row_count=len(records),
            cache_hit=True,
            snapshot_path=str(latest) if latest else None,
            records=records,
        )

    def _fetch_or_cache(
        self,
        *,
        dataset_name: str,
        trade_date: str,
        ts_codes: Iterable[str] | None,
        force_refresh: bool,
    ) -> TushareDragonTigerSnapshotResult:
        if not force_refresh:
            cached = self._load_cached(dataset_name=dataset_name, trade_date=trade_date)
            if cached is not None:
                return cached

        if dataset_name == "dragon_tiger_top_list":
            frame = self.adapter.fetch_top_list(trade_date, ts_codes)
            owned_fields = [
                "stock_id",
                "stock_name",
                "close_price",
                "pct_chg",
                "dragon_tiger_turnover_rate",
                "amount",
                "dragon_tiger_sell_amount",
                "dragon_tiger_buy_amount",
                "dragon_tiger_net_amount",
                "dragon_tiger_amount_rate",
                "dragon_tiger_net_rate",
                "dragon_tiger_reason",
            ]
        elif dataset_name == "dragon_tiger_top_inst":
            frame = self.adapter.fetch_top_inst(trade_date, ts_codes)
            owned_fields = [
                "stock_id",
                "dragon_tiger_seat_name",
                "dragon_tiger_seat_side",
                "dragon_tiger_buy_amount",
                "dragon_tiger_sell_amount",
                "dragon_tiger_seat_net_buy",
                "dragon_tiger_reason",
            ]
        else:
            raise ValueError(f"unsupported dataset_name: {dataset_name}")

        records = TushareAdapter.to_records(frame)
        batch_id = datetime.now().strftime(f"{dataset_name}_%Y%m%d%H%M%S")
        ingest = self.ingest_service.capture_snapshot(
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
        return TushareDragonTigerSnapshotResult(
            trade_date=trade_date,
            dataset_name=dataset_name,
            row_count=len(records),
            cache_hit=False,
            snapshot_path=ingest.snapshot_path,
            records=records,
        )
