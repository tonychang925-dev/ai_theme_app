from __future__ import annotations

from dataclasses import replace
from datetime import date

from stock_processing_service.contracts.dto import SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


class StrongWatchRollForwardService:
    def roll_forward(
        self,
        *,
        trade_date: date,
        seeded_rows: list[SubjectStockPoolDTO],
        prior_active_rows: list[StrongWatchRecord],
    ) -> list[StrongWatchRecord]:
        baseline: list[StrongWatchRecord] = []
        for row in prior_active_rows:
            if row.watch_status not in {"active", "weakening"}:
                continue
            baseline.append(
                replace(
                    row,
                    watch_status="pending_refresh",
                    watch_age_days=max(int(row.watch_age_days or 1) + 1, 1),
                    prune_mode=None,
                    prune_reason_code=None,
                    removed_reason=None,
                )
            )
        return baseline
