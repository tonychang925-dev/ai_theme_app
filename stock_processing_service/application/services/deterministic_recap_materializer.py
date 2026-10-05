"""Deterministic, read-model-only recap materialization.

This path deliberately delegates fact assembly to ``BuildPostMarketRecapJob``
with its deterministic switches enabled.  It never runs prerequisite builders,
LLM services, cache/event writes, or the mainline durable projections.
"""

from __future__ import annotations

from datetime import date
from typing import Any


class DeterministicRecapMaterializer:
    """Single-date materializer used by the #445 canary and dry-run."""

    def __init__(self, recap_job: Any) -> None:
        self._recap_job = recap_job

    async def materialize(self, trade_date: date, *, dry_run: bool = False) -> dict[str, Any]:
        snapshot_version = f"deterministic_recap.v1.{trade_date:%Y%m%d}"
        run_id = f"deterministic-recap-{trade_date:%Y%m%d}"
        result = await self._recap_job.execute(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=run_id,
            trace_id=run_id,
            lookback_days=7,
            skip_prereqs=True,
            skip_layer_c=True,
            deterministic_only=True,
            write_snapshot=not dry_run,
        )
        snapshot = self._recap_job.last_materialized_snapshot
        return {
            "ok": result.status == "ok",
            "status": "dry_run" if dry_run and result.status == "ok" else result.status,
            "trade_date": trade_date.isoformat(),
            "snapshot_version": snapshot_version,
            "affected_rows": 0 if dry_run else result.affected_rows,
            "metrics": dict(result.metrics or {}),
            "warnings": list(result.warnings or []),
            "write_scope": ["post_market_recap_snapshot"] if result.status == "ok" and not dry_run else [],
            "llm_call": False,
            "derived_rebuild": False,
            "snapshot": snapshot.recap_doc if snapshot is not None else None,
        }
