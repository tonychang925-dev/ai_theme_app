from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from stock_processing_service.application.replay import ReplayLayerManifest


class ReplayManifestGateway(Protocol):
    async def get_replay_snapshot_manifest(
        self,
        trade_date: date,
        layer_name: str,
        snapshot_version: str,
        algorithm_version: str,
    ) -> dict[str, Any] | None: ...

    async def upsert_replay_snapshot_manifest(self, row: dict[str, Any]) -> int: ...


class ReplayManifestGatewayAdapter:
    """PostgreSQL-backed ReplayManifestStore adapter."""

    def __init__(self, db_gateway: ReplayManifestGateway) -> None:
        self._db = db_gateway

    async def get_layer_manifest(
        self,
        *,
        trade_date: date,
        layer_name: str,
        snapshot_version: str,
        algorithm_version: str,
    ) -> ReplayLayerManifest | None:
        row = await self._db.get_replay_snapshot_manifest(
            trade_date=trade_date,
            layer_name=layer_name,
            snapshot_version=snapshot_version,
            algorithm_version=algorithm_version,
        )
        if not row:
            return None
        return ReplayLayerManifest(
            trade_date=row.get("trade_date", trade_date),
            layer_name=str(row.get("layer_name") or layer_name),
            snapshot_version=str(row.get("snapshot_version") or snapshot_version),
            algorithm_version=str(row.get("algorithm_version") or algorithm_version),
            input_hash=str(row.get("input_hash") or ""),
            output_hash=str(row.get("output_hash") or ""),
            row_count=int(row.get("row_count") or 0),
            status=str(row.get("status") or ""),
            batch_id=str(row.get("batch_id") or ""),
            trace_id=str(row.get("trace_id") or ""),
            created_at=row.get("created_at"),
        )

    async def upsert_layer_manifest(self, manifest: ReplayLayerManifest) -> int:
        return await self._db.upsert_replay_snapshot_manifest(
            {
                "trade_date": manifest.trade_date,
                "layer_name": manifest.layer_name,
                "snapshot_version": manifest.snapshot_version,
                "algorithm_version": manifest.algorithm_version,
                "input_hash": manifest.input_hash,
                "output_hash": manifest.output_hash,
                "row_count": manifest.row_count,
                "status": manifest.status,
                "batch_id": manifest.batch_id,
                "trace_id": manifest.trace_id,
            }
        )
