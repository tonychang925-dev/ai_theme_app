from __future__ import annotations

from stock_processing_service.contracts.dto import SubjectStockPoolDTO


class StrongWatchSeedService:
    @staticmethod
    def _is_disallowed(stock_id: str, stock_name: str) -> bool:
        sid = str(stock_id or "").upper()
        code = sid.split(".", 1)[0]
        if code.startswith("688"):
            return True
        name = str(stock_name or "").strip().upper()
        if name.startswith("ST") or name.startswith("*ST"):
            return True
        return False

    def seed(self, pool_rows: list[SubjectStockPoolDTO]) -> list[SubjectStockPoolDTO]:
        # Keep strong-pool candidates with old-chain compatible hard gates:
        # rank gate + 688/ST exclusion + dedupe by stock_id.
        selected: dict[str, SubjectStockPoolDTO] = {}
        for row in pool_rows:
            rank = row.pool_rank if row.pool_rank is not None else 999
            if rank > 30:
                continue
            if self._is_disallowed(row.stock_id, row.stock_name or ""):
                continue
            if not str(row.stock_id or ""):
                continue
            selected.setdefault(row.stock_id, row)
        return list(selected.values())
