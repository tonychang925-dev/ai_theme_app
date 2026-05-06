from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ReplayLayerManifest:
    trade_date: date
    layer_name: str
    snapshot_version: str
    algorithm_version: str
    input_hash: str = ""
    output_hash: str = ""
    row_count: int = 0
    status: str = "ok"
    batch_id: str = ""
    trace_id: str = ""
    created_at: datetime | None = None

    def reusable_for(self, *, input_hash: str, strict: bool = True) -> bool:
        if self.status != "ok":
            return False
        if strict and not input_hash:
            return False
        return (not input_hash) or self.input_hash == input_hash


class ReplayManifestStore(Protocol):
    async def get_layer_manifest(
        self,
        *,
        trade_date: date,
        layer_name: str,
        snapshot_version: str,
        algorithm_version: str,
    ) -> ReplayLayerManifest | None: ...

    async def upsert_layer_manifest(self, manifest: ReplayLayerManifest) -> int: ...


class InMemoryReplayManifestStore:
    """Small test/dev manifest store.

    Production should use the `replay_snapshot_manifest` table via database_service.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[date, str, str, str], ReplayLayerManifest] = {}

    async def get_layer_manifest(
        self,
        *,
        trade_date: date,
        layer_name: str,
        snapshot_version: str,
        algorithm_version: str,
    ) -> ReplayLayerManifest | None:
        return self._rows.get((trade_date, layer_name, snapshot_version, algorithm_version))

    async def upsert_layer_manifest(self, manifest: ReplayLayerManifest) -> int:
        self._rows[
            (
                manifest.trade_date,
                manifest.layer_name,
                manifest.snapshot_version,
                manifest.algorithm_version,
            )
        ] = manifest
        return 1

    def as_rows(self) -> list[dict[str, Any]]:
        return [
            {
                "trade_date": row.trade_date.isoformat(),
                "layer_name": row.layer_name,
                "snapshot_version": row.snapshot_version,
                "algorithm_version": row.algorithm_version,
                "input_hash": row.input_hash,
                "output_hash": row.output_hash,
                "row_count": row.row_count,
                "status": row.status,
                "batch_id": row.batch_id,
                "trace_id": row.trace_id,
            }
            for row in self._rows.values()
        ]
