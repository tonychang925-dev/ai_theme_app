from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import StockBarDTO, SubjectStockPoolDTO


@dataclass(frozen=True)
class LeaderEvidence:
    leader_alive_score: Decimal
    leader_breakdown_flag: bool
    relay_strength_score: Decimal
    front_row_survival_ratio: Decimal
    successor_vacuum: bool
    leader_breakdown_reason: str
    leader_score_source: str
    leader_stock_id: str | None
    leader_stock_name: str | None
    leader_pct_chg: Decimal | None
    leader_limit_up: bool
    front_row_alive_count: int
    front_row_limit_up_count: int
    front_row_big_drop_count: int


class LeaderEvidenceBuilder:
    """Build Layer B leader evidence from subject pool rows and daily bars."""

    FRONT_ROW_SIZE = 5

    def build(
        self,
        *,
        rows: list[SubjectStockPoolDTO],
        bars_by_stock: dict[str, StockBarDTO],
    ) -> LeaderEvidence:
        if not rows:
            return LeaderEvidence(
                leader_alive_score=Decimal("0"),
                leader_breakdown_flag=True,
                relay_strength_score=Decimal("0"),
                front_row_survival_ratio=Decimal("0"),
                successor_vacuum=True,
                leader_breakdown_reason="leader_row_missing",
                leader_score_source="missing",
                leader_stock_id=None,
                leader_stock_name=None,
                leader_pct_chg=None,
                leader_limit_up=False,
                front_row_alive_count=0,
                front_row_limit_up_count=0,
                front_row_big_drop_count=0,
            )

        scored_rows = [(self._row_score(row, bars_by_stock.get(row.stock_id)), row) for row in rows]
        explicit_scores = [(score, row) for score, row in scored_rows if self._explicit_leader_score(row) is not None]
        leader_score, leader = max(explicit_scores or scored_rows, key=lambda item: (item[0], -self._rank(item[1])))
        front_rows = sorted(rows, key=self._rank)[: self.FRONT_ROW_SIZE]

        front_alive_count = 0
        front_limit_up_count = 0
        front_big_drop_count = 0
        for row in front_rows:
            bar = bars_by_stock.get(row.stock_id)
            pct = self._pct(row, bar)
            if pct >= Decimal("0"):
                front_alive_count += 1
            if self._limit_up(row, bar, pct):
                front_limit_up_count += 1
            if pct <= Decimal("-5"):
                front_big_drop_count += 1

        front_total = max(len(front_rows), 1)
        front_row_survival = Decimal(str(front_alive_count)) / Decimal(str(front_total))
        leader_bar = bars_by_stock.get(leader.stock_id)
        leader_pct = self._pct(leader, leader_bar)
        leader_limit_up = self._limit_up(leader, leader_bar, leader_pct)
        leader_big_drop = leader_pct <= Decimal("-5")
        sorted_scores = sorted((score for score, _ in scored_rows), reverse=True)
        relay_pool = sorted_scores[1:6] if len(sorted_scores) > 1 else []
        relay_strength = (
            sum(relay_pool, start=Decimal("0")) / Decimal(str(max(len(relay_pool), 1)))
            if relay_pool
            else Decimal("0")
        )
        successor_vacuum = front_alive_count <= 1 and front_limit_up_count == 0 and not leader_limit_up
        leader_breakdown = leader_score < Decimal("50") and front_row_survival < Decimal("0.4") and not leader_limit_up

        return LeaderEvidence(
            leader_alive_score=leader_score,
            leader_breakdown_flag=leader_breakdown,
            relay_strength_score=relay_strength,
            front_row_survival_ratio=front_row_survival,
            successor_vacuum=successor_vacuum,
            leader_breakdown_reason=self._breakdown_reason(
                leader_score=leader_score,
                leader_pct=leader_pct,
                leader_limit_up=leader_limit_up,
                leader_big_drop=leader_big_drop,
                successor_vacuum=successor_vacuum,
                explicit=bool(explicit_scores),
            ),
            leader_score_source="pool_metadata" if explicit_scores else "db_pool_fields_inferred",
            leader_stock_id=leader.stock_id,
            leader_stock_name=leader.stock_name,
            leader_pct_chg=leader_pct,
            leader_limit_up=leader_limit_up,
            front_row_alive_count=front_alive_count,
            front_row_limit_up_count=front_limit_up_count,
            front_row_big_drop_count=front_big_drop_count,
        )

    def _row_score(self, row: SubjectStockPoolDTO, bar: StockBarDTO | None) -> Decimal:
        explicit = self._explicit_leader_score(row)
        if explicit is not None:
            return explicit
        pct = self._pct(row, bar)
        score = self._pct_score(pct=pct, limit_up=self._limit_up(row, bar, pct))
        rank = self._rank(row)
        if rank <= 1:
            score += Decimal("20")
        elif rank <= 3:
            score += Decimal("15")
        elif rank <= 5:
            score += Decimal("10")
        if self._bool((row.metadata or {}).get("is_leader")):
            score += Decimal("10")
        return min(Decimal("100"), score)

    @staticmethod
    def _pct_score(*, pct: Decimal, limit_up: bool) -> Decimal:
        if limit_up or pct >= Decimal("9.5"):
            return Decimal("70")
        if pct >= Decimal("7"):
            return Decimal("60")
        if pct >= Decimal("5"):
            return Decimal("50")
        if pct >= Decimal("3"):
            return Decimal("42")
        if pct >= Decimal("0"):
            return Decimal("30")
        if pct >= Decimal("-3"):
            return Decimal("15")
        return Decimal("0")

    @classmethod
    def _explicit_leader_score(cls, row: SubjectStockPoolDTO) -> Decimal | None:
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        for key in ("leader_score", "leader_alive_score", "front_rank_alive_score"):
            value = metadata.get(key)
            if value not in (None, ""):
                return cls._d(value)
        return None

    @classmethod
    def _pct(cls, row: SubjectStockPoolDTO, bar: StockBarDTO | None) -> Decimal:
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        if bar is not None:
            return cls._d(bar.pct_chg)
        return cls._d(metadata.get("pct_chg"))

    @classmethod
    def _limit_up(cls, row: SubjectStockPoolDTO, bar: StockBarDTO | None, pct: Decimal) -> bool:
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        if "limit_up" in metadata:
            return cls._bool(metadata.get("limit_up"))
        if bar is not None:
            return pct >= Decimal("9.5") or (bar.limit_up_price > 0 and bar.close_price >= bar.limit_up_price)
        return pct >= Decimal("9.5")

    @staticmethod
    def _rank(row: SubjectStockPoolDTO) -> int:
        metadata = row.metadata if isinstance(row.metadata, dict) else {}
        value = row.pool_rank if row.pool_rank is not None else metadata.get("rank_order") or metadata.get("pool_rank")
        try:
            return int(value or 999)
        except (TypeError, ValueError):
            return 999

    @staticmethod
    def _breakdown_reason(
        *,
        leader_score: Decimal,
        leader_pct: Decimal,
        leader_limit_up: bool,
        leader_big_drop: bool,
        successor_vacuum: bool,
        explicit: bool,
    ) -> str:
        if leader_limit_up:
            return "leader_limit_up_alive"
        if leader_big_drop:
            return "leader_big_drop"
        if successor_vacuum:
            return "successor_vacuum"
        if leader_score < Decimal("50"):
            return "leader_score_below_50" if explicit else "inferred_leader_score_below_50"
        return "pool_metadata_alive" if explicit else "db_pool_fields_inferred_alive"

    @staticmethod
    def _d(value: Any) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "y"}
        return bool(value)
