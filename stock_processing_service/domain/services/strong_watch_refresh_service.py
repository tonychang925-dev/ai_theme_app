from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

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
    support_type: str
    support_level: Decimal
    support_score: Decimal
    support_refs: list[str] = field(default_factory=list)
    role_tags: dict[str, Any] = field(default_factory=dict)
    watch_status: str = "active"
    weak_days: int = 0
    prune_reason_code: str | None = None
    prune_mode: str | None = None
    removed_reason: str | None = None
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
            momentum_score = max(Decimal("0"), min(Decimal("100"), bar.pct_chg * Decimal("10") + Decimal("50")))
            ma_support = bar.close_price * Decimal("0.97")
            prev_low_support = bar.low_price
            platform_support = (bar.open_price + bar.pre_close) / Decimal("2")
            support_level = max(ma_support, prev_low_support, platform_support)

            if support_level == ma_support:
                support_type = "ma_support"
            elif support_level == prev_low_support:
                support_type = "prev_low_support"
            else:
                support_type = "platform_support"

            support_distance = (bar.close_price - support_level) / (bar.close_price if bar.close_price != 0 else Decimal("1"))
            support_score = max(
                Decimal("0"),
                min(
                    Decimal("100"),
                    Decimal("100") - abs(support_distance * Decimal("260")),
                ),
            )
            watch_score = rank_score * Decimal("0.35") + momentum_score * Decimal("0.35") + support_score * Decimal("0.30")
            support_refs = [
                f"close={bar.close_price}",
                f"ma_support={ma_support}",
                f"prev_low_support={prev_low_support}",
                f"platform_support={platform_support}",
                f"selected={support_type}:{support_level}",
            ]

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
                    support_type=support_type,
                    support_level=support_level,
                    support_score=support_score,
                    support_refs=support_refs,
                    role_tags={
                        "watch_tier": grade,
                        "is_leader": bool((row.pool_rank or 999) <= 1),
                        "momentum_positive": bool(bar.pct_chg > Decimal("0")),
                    },
                )
            )
        return rows
