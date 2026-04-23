from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.domain.policies.stock_filters import is_excluded_stock
from stock_processing_service.ports.cache_ports import CachePorts
from stock_processing_service.ports.read_ports import StockReadPorts
from stock_processing_service.ports.write_ports import StockWritePorts


@dataclass(slots=True)
class BuildStrongStockTrackingUseCase:
    """Build strong-stock tracking objects for a given trade date.

    Current scope is skeleton-only: wiring, guardrails, and filter behavior.
    """

    read_ports: StockReadPorts
    write_ports: StockWritePorts
    cache_ports: CachePorts | None = None

    async def execute(self, trade_date: date, window_days: int = 7) -> BuildResult:
        if window_days not in (7, 10, 15, 20):
            raise ValueError(f"unsupported window_days: {window_days}")

        # TODO: replace with real assembly from daily snapshots + theme pools.
        theme_pool = await self.read_ports.get_subject_stock_pool_by_trade_date(trade_date)

        filtered_rows: list[dict[str, Any]] = []
        for row in theme_pool:
            stock_code = str(row.get("stock_code") or row.get("stock_id") or "")
            stock_name = str(row.get("stock_name", ""))
            if is_excluded_stock(stock_code):
                continue
            if "ST" in stock_name.upper():
                continue
            filtered_rows.append(row)

        # TODO: apply "first-selection only" dedup logic here.
        affected = await self.write_ports.upsert_stock_daily_snapshot_rows(filtered_rows)

        return BuildResult(
            name="build_strong_stock_tracking",
            trade_date=trade_date.isoformat(),
            affected_rows=affected,
            status="ok",
        )
