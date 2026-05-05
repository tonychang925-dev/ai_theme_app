from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidence


@dataclass(frozen=True)
class SubjectBoardStructure:
    """题材板块结构指标（对齐生产 ThemeBoardStructureAggregator）。"""
    subject_key: str
    limit_up_count: int
    limit_down_count: int
    red_ratio: Decimal
    big_drop_ratio: Decimal
    front_row_strength_score: Decimal
    front_row_survival_ratio: Decimal
    front_row_count: int
    total_stock_count: int
    leader_breakdown_flag: bool


class SubjectBoardStructureAggregator:
    """题材板块结构聚合器。

    从 per-stock CycleEvidence 聚合计算板块级指标：
    - 涨停/跌停计数
    - 红盘率 / 大跌比
    - 前排强度 / 前排存活率
    - 龙头失位检测

    对齐生产板块结构聚合口径。
    """

    FRONT_ROW_SIZE = 3

    def aggregate(
        self,
        subject_key: str,
        stock_rows: list[CycleEvidence],
    ) -> SubjectBoardStructure:
        n = max(len(stock_rows), 1)
        rows_sorted = sorted(stock_rows, key=lambda r: r.leader_score, reverse=True)

        limit_up_count = sum(1 for r in rows_sorted if r.pct_chg >= Decimal("9.5"))
        limit_down_count = sum(1 for r in rows_sorted if r.pct_chg <= Decimal("-9.5"))
        red_ratio = Decimal(str(sum(1 for r in rows_sorted if r.pct_chg > 0) / n))
        big_drop_ratio = Decimal(str(sum(1 for r in rows_sorted if r.pct_chg <= Decimal("-5")) / n))

        front_rows = rows_sorted[: min(self.FRONT_ROW_SIZE, len(rows_sorted))]
        front_total = max(len(front_rows), 1)
        front_alive = sum(
            1 for r in front_rows
            if r.pct_chg >= Decimal("0") or r.leader_score >= Decimal("40")
        )
        front_row_survival_ratio = Decimal(str(front_alive / front_total))
        front_row_strength_score = (
            sum((r.board_score for r in front_rows), start=Decimal("0"))
            / Decimal(str(front_total))
        )
        leader_breakdown_flag = any(
            r.pct_chg <= Decimal("-7") for r in front_rows
        )

        return SubjectBoardStructure(
            subject_key=subject_key,
            limit_up_count=limit_up_count,
            limit_down_count=limit_down_count,
            red_ratio=red_ratio,
            big_drop_ratio=big_drop_ratio,
            front_row_strength_score=front_row_strength_score,
            front_row_survival_ratio=front_row_survival_ratio,
            front_row_count=len(front_rows),
            total_stock_count=len(rows_sorted),
            leader_breakdown_flag=leader_breakdown_flag,
        )
