from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


@dataclass(frozen=True)
class StrongWatchHistoryRecord:
    trade_date: date
    stock_id: str
    subject_key: str
    watch_status: str
    strong_grade: str
    watch_score: Decimal
    support_score: Decimal
    support_type: str
    prune_mode: str | None = None
    prune_reason_code: str | None = None
    removed_reason: str | None = None
    kept_because: str | None = None


class StrongWatchHistoryService:
    def build_history_snapshot(
        self,
        trade_date: date,
        kept_rows: list[StrongWatchRecord],
        pruned_rows: list[StrongWatchRecord],
    ) -> list[StrongWatchHistoryRecord]:
        rows: list[StrongWatchHistoryRecord] = []
        for row in [*kept_rows, *pruned_rows]:
            rows.append(
                StrongWatchHistoryRecord(
                    trade_date=trade_date,
                    stock_id=row.stock_id,
                    subject_key=row.subject_key,
                    watch_status=row.watch_status,
                    strong_grade=row.strong_grade,
                    watch_score=row.watch_score,
                    support_score=row.support_score,
                    support_type=row.support_type,
                    prune_mode=row.prune_mode,
                    prune_reason_code=row.prune_reason_code,
                    removed_reason=row.removed_reason,
                    kept_because=row.kept_because,
                )
            )
        return rows
