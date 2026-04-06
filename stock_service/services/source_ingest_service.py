from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from stock_service.config import StockServiceConfig
from stock_service.raw_snapshot_store import RawSnapshotRecord, RawSnapshotStore
from stock_service.source_contract import DEFAULT_SOURCE_OWNERSHIP, SourceOwnershipRegistry


@dataclass(frozen=True)
class SourceIngestResult:
    source_name: str
    dataset_name: str
    trade_date: str
    batch_id: str
    snapshot_path: str
    row_count: int


class SourceIngestService:
    def __init__(
        self,
        config: StockServiceConfig,
        ownership: SourceOwnershipRegistry = DEFAULT_SOURCE_OWNERSHIP,
    ):
        self.config = config
        self.ownership = ownership
        self.snapshot_store = RawSnapshotStore(config.raw_snapshot_root)

    def capture_snapshot(
        self,
        *,
        source_name: str,
        dataset_name: str,
        trade_date: str,
        batch_id: str,
        payload: Any,
        owned_fields: Iterable[str],
        metadata: dict[str, Any] | None = None,
    ) -> SourceIngestResult:
        self.ownership.validate_payload(owned_fields, source_name)
        record: RawSnapshotRecord = self.snapshot_store.write_json_snapshot(
            source_name=source_name,
            dataset_name=dataset_name,
            trade_date=trade_date,
            batch_id=batch_id,
            payload=payload,
            metadata=metadata,
        )
        return SourceIngestResult(
            source_name=record.source_name,
            dataset_name=record.dataset_name,
            trade_date=record.trade_date,
            batch_id=record.batch_id,
            snapshot_path=str(record.path),
            row_count=record.row_count,
        )
