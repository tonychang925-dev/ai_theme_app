from __future__ import annotations

from stock_processing_service.contracts.dto import SubjectStockPoolDTO


class StrongWatchSeedService:
    def seed(self, pool_rows: list[SubjectStockPoolDTO]) -> list[SubjectStockPoolDTO]:
        # Keep strong-pool candidates with basic rank gate and dedupe by stock_id.
        selected: dict[str, SubjectStockPoolDTO] = {}
        for row in pool_rows:
            rank = row.pool_rank if row.pool_rank is not None else 999
            if rank > 30:
                continue
            selected.setdefault(row.stock_id, row)
        return list(selected.values())
