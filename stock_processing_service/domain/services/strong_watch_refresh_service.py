from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.contracts.dto import StockBarDTO, SubjectStockPoolDTO


@dataclass(frozen=True)
class StrongWatchRecord:
    stock_id: str
    stock_name: str
    subject_key: str
    subject_name: str
    pool_rank: int | None
    watch_score: Decimal
    strong_grade: str
    source: str = "strong_watch_pool"


class StrongWatchRefreshService:
    def refresh(
        self,
        seeded_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
    ) -> list[StrongWatchRecord]:
        bars_by_stock = {bar.stock_id: bar for bar in bars}
        rows: list[StrongWatchRecord] = []
        for row in seeded_rows:
            bar = bars_by_stock.get(row.stock_id)
            if bar is None:
                continue
            rank = row.pool_rank if row.pool_rank is not None else 20
            rank_score = Decimal("100") / Decimal(str(max(rank, 1)))
            momentum = max(Decimal("0"), min(Decimal("100"), bar.pct_chg * Decimal("10") + Decimal("50")))
            watch_score = rank_score * Decimal("0.55") + momentum * Decimal("0.45")

            if watch_score >= Decimal("80"):
                grade = "S"
            elif watch_score >= Decimal("65"):
                grade = "A"
            elif watch_score >= Decimal("50"):
                grade = "B"
            else:
                grade = "REJECT"

            rows.append(
                StrongWatchRecord(
                    stock_id=row.stock_id,
                    stock_name=row.stock_name or bar.stock_name,
                    subject_key=row.subject_key,
                    subject_name=row.subject_name,
                    pool_rank=row.pool_rank,
                    watch_score=watch_score,
                    strong_grade=grade,
                )
            )
        return rows
