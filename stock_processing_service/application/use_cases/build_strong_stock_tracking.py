from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from stock_processing_service.contracts.dto import BuildResult
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

        # Truth safety hard-stop:
        # this use case is object-layer only and must never write stock_daily_snapshot.
        # Keep this explicit failure until a dedicated object table/write-path is implemented.
        raise RuntimeError(
            "BuildStrongStockTrackingUseCase is disabled for truth safety: "
            "object-layer flow must not call upsert_stock_daily_snapshot_rows"
        )

        # Unreachable (kept for future object-layer implementation).
