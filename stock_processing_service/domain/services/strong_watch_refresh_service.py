from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.kline_support_scorer import KlineSupportScorer


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
    support_count: int = 0
    support_combined_strength: Decimal = Decimal("0")
    gap_hit: bool = False
    gap_hit_mode: str = "miss"
    gap_source: str = ""
    gap_level: Decimal = Decimal("0")
    gap_distance_pct: Decimal = Decimal("999")
    role_tags: dict[str, Any] = field(default_factory=dict)
    watch_status: str = "active"
    weak_days: int = 0
    prune_reason_code: str | None = None
    prune_mode: str | None = None
    removed_reason: str | None = None
    source: str = "strong_watch_pool"
    mainline_context_score: Decimal = Decimal("0")
    strong_gene_score: Decimal = Decimal("0")
    weakness_tolerance_score: Decimal = Decimal("0")
    prior7_limitup_days: int = 0
    prior7_strong_days: int = 0
    prior7_best_watch_score: Decimal = Decimal("0")
    prior7_peak_rank: int = 99
    kept_because: str | None = None


class StrongWatchRefreshService:
    def __init__(self, support_scorer: KlineSupportScorer | None = None) -> None:
        self._support_scorer = support_scorer or KlineSupportScorer()

    @staticmethod
    def _d(value: Any, default: str = "0") -> Decimal:
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    @staticmethod
    def _in_range(value: Decimal, low: str, high: str) -> bool:
        return Decimal(low) <= value <= Decimal(high)

    def _weakness_tolerance_score(self, pct_chg: Decimal) -> Decimal:
        # Weak-to-strong upstream should tolerate pullback and neutral days,
        # while avoiding overheating and extreme breakdown.
        if self._in_range(pct_chg, "-5", "-1"):
            return Decimal("92")
        if self._in_range(pct_chg, "-1", "2"):
            return Decimal("76")
        if self._in_range(pct_chg, "2", "4"):
            return Decimal("56")
        if pct_chg > Decimal("4"):
            return Decimal("36")
        if self._in_range(pct_chg, "-8", "-5"):
            return Decimal("52")
        return Decimal("24")

    def _mainline_context_score(self, rank: int, metadata: dict[str, Any]) -> Decimal:
        rank_score = Decimal("100") / Decimal(str(max(rank, 1)))
        role_tags = metadata.get("role_tags") if isinstance(metadata.get("role_tags"), dict) else {}
        leader_bonus = Decimal("14") if bool(role_tags.get("is_leader")) else Decimal("0")
        front_row_bonus = Decimal("8") if bool(role_tags.get("is_front_row_core")) else Decimal("0")
        return min(Decimal("100"), rank_score * Decimal("0.72") + leader_bonus + front_row_bonus)

    def _prior7_features(
        self,
        *,
        stock_id: str,
        metadata: dict[str, Any],
        prior_rows_by_stock: dict[str, list[PriorSnapshotDTO]],
    ) -> tuple[int, int, Decimal, int]:
        m_limit = metadata.get("prior7_limitup_days")
        m_strong = metadata.get("prior7_strong_days")
        m_best_watch = metadata.get("prior7_best_watch_score")
        m_peak_rank = metadata.get("prior7_peak_rank")
        if m_limit is not None or m_strong is not None or m_best_watch is not None or m_peak_rank is not None:
            return (
                int(m_limit or 0),
                int(m_strong or 0),
                self._d(m_best_watch),
                int(m_peak_rank or 99),
            )

        rows = prior_rows_by_stock.get(stock_id, [])
        limitup_days = 0
        strong_days = 0
        best_watch_score = Decimal("0")
        peak_rank = 99
        for r in rows:
            payload = r.payload or {}
            pct = self._d(payload.get("pct_chg"))
            if pct >= Decimal("9.5"):
                limitup_days += 1
            if pct >= Decimal("5"):
                strong_days += 1
            best_watch_score = max(best_watch_score, self._d(payload.get("watch_score")))
            rank = int(payload.get("pool_rank") or 99)
            peak_rank = min(peak_rank, rank)
        return limitup_days, strong_days, best_watch_score, peak_rank

    def _strong_gene_score(
        self,
        *,
        prior7_limitup_days: int,
        prior7_strong_days: int,
        prior7_best_watch_score: Decimal,
        prior7_peak_rank: int,
    ) -> Decimal:
        history_score = min(
            Decimal("100"),
            Decimal(str(prior7_limitup_days * 25 + prior7_strong_days * 10)),
        )
        best_watch_bonus = min(Decimal("20"), prior7_best_watch_score * Decimal("0.2"))
        peak_rank_bonus = Decimal("10") if prior7_peak_rank <= 3 else Decimal("0")
        return min(
            Decimal("100"),
            history_score + best_watch_bonus + peak_rank_bonus,
        )

    def refresh(
        self,
        seeded_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
    ) -> list[StrongWatchRecord]:
        bars_by_stock = {bar.stock_id: bar for bar in bars}
        history_bars_by_stock: dict[str, list[StockBarDTO]] = {}
        for hist in history_bars or []:
            history_bars_by_stock.setdefault(hist.stock_id, []).append(hist)
        prior_rows_by_stock: dict[str, list[PriorSnapshotDTO]] = {}
        for prior in prior_rows or []:
            prior_rows_by_stock.setdefault(prior.stock_id, []).append(prior)
        rows: list[StrongWatchRecord] = []
        for row in seeded_rows:
            bar = bars_by_stock.get(row.stock_id)
            if bar is None:
                continue
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            rank = row.pool_rank if row.pool_rank is not None else 20
            mainline_context_score = self._mainline_context_score(rank, metadata)
            weakness_tolerance_score = self._weakness_tolerance_score(bar.pct_chg)
            prior7_limitup_days, prior7_strong_days, prior7_best_watch_score, prior7_peak_rank = self._prior7_features(
                stock_id=row.stock_id,
                metadata=metadata,
                prior_rows_by_stock=prior_rows_by_stock,
            )
            strong_gene_score = self._strong_gene_score(
                prior7_limitup_days=prior7_limitup_days,
                prior7_strong_days=prior7_strong_days,
                prior7_best_watch_score=prior7_best_watch_score,
                prior7_peak_rank=prior7_peak_rank,
            )

            support_result = self._support_scorer.score(
                stock_id=row.stock_id,
                current_bar=bar,
                prior_rows=prior_rows_by_stock.get(row.stock_id, []),
                history_bars=history_bars_by_stock.get(row.stock_id, []),
            )
            support_type = support_result.support_type
            support_level = support_result.support_level
            support_score = support_result.support_score
            support_refs = list(support_result.support_refs)
            support_count = support_result.support_count
            support_combined_strength = support_result.combined_strength
            gap_hit = support_result.gap_hit
            gap_hit_mode = support_result.gap_hit_mode
            gap_source = support_result.gap_source
            gap_level = support_result.gap_level
            gap_distance_pct = support_result.gap_distance_pct
            watch_score = (
                mainline_context_score * Decimal("0.20")
                + strong_gene_score * Decimal("0.35")
                + support_score * Decimal("0.25")
                + weakness_tolerance_score * Decimal("0.20")
            )

            if watch_score >= Decimal("78"):
                grade = "S"
            elif watch_score >= Decimal("66"):
                grade = "A"
            elif watch_score >= Decimal("54"):
                grade = "B"
            elif watch_score >= Decimal("42"):
                grade = "B_KEEP"
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
                    support_count=support_count,
                    support_combined_strength=support_combined_strength,
                    gap_hit=gap_hit,
                    gap_hit_mode=gap_hit_mode,
                    gap_source=gap_source,
                    gap_level=gap_level,
                    gap_distance_pct=gap_distance_pct,
                    role_tags={
                        "watch_tier": grade,
                        "is_leader": bool((row.pool_rank or 999) <= 1),
                        "is_front_row_core": bool((row.pool_rank or 999) <= 3),
                        "momentum_positive": bool(bar.pct_chg > Decimal("0")),
                        "prior7_limitup_days": prior7_limitup_days,
                        "prior7_strong_days": prior7_strong_days,
                        "prior7_best_watch_score": str(prior7_best_watch_score),
                        "prior7_peak_rank": prior7_peak_rank,
                    },
                    mainline_context_score=mainline_context_score,
                    strong_gene_score=strong_gene_score,
                    weakness_tolerance_score=weakness_tolerance_score,
                    prior7_limitup_days=prior7_limitup_days,
                    prior7_strong_days=prior7_strong_days,
                    prior7_best_watch_score=prior7_best_watch_score,
                    prior7_peak_rank=prior7_peak_rank,
                )
            )
        return rows
