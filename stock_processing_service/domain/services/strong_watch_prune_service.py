from __future__ import annotations

from stock_processing_service.domain.services.strong_watch_refresh_service import StrongWatchRecord


class StrongWatchPruneService:
    def prune(self, rows: list[StrongWatchRecord]) -> list[StrongWatchRecord]:
        return [row for row in rows if row.strong_grade != "REJECT"]
