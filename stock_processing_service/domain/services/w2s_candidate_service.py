from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO


@dataclass(frozen=True)
class W2SCandidate:
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    subject_name: str
    support_score: Decimal
    momentum_score: Decimal
    candidate_score: Decimal
    candidate_level: str
    evidence_rules: list[str]


class W2SCandidateService:
    def build_candidates(
        self,
        bars: list[StockBarDTO],
        pool_rows: list[SubjectStockPoolDTO],
        prior_rows: list[PriorSnapshotDTO],
    ) -> list[W2SCandidate]:
        bar_by_stock = {bar.stock_id: bar for bar in bars}
        prior_by_stock = {row.stock_id: row for row in prior_rows}

        candidates: list[W2SCandidate] = []
        for row in pool_rows:
            bar = bar_by_stock.get(row.stock_id)
            if bar is None:
                continue

            support_score = Decimal("100") / Decimal(str(max(row.pool_rank or 10, 1)))
            momentum_score = max(Decimal("0"), min(Decimal("100"), bar.pct_chg * Decimal("10") + Decimal("50")))

            prior_state = ""
            prior = prior_by_stock.get(row.stock_id)
            if prior:
                prior_state = str(prior.payload.get("final_cycle_state", ""))

            continuity_bonus = Decimal("10") if prior_state in {"repair", "fade_watch"} else Decimal("0")
            candidate_score = support_score * Decimal("0.45") + momentum_score * Decimal("0.45") + continuity_bonus

            if candidate_score >= Decimal("75"):
                level = "A"
            elif candidate_score >= Decimal("65"):
                level = "B"
            elif candidate_score >= Decimal("55"):
                level = "C"
            else:
                continue

            evidence = [
                f"pool_rank={row.pool_rank}",
                f"pct_chg={bar.pct_chg}",
                f"prior_state={prior_state or 'unknown'}",
            ]
            candidates.append(
                W2SCandidate(
                    trade_date=str(row.trade_date),
                    stock_id=row.stock_id,
                    stock_name=row.stock_name or bar.stock_name,
                    subject_key=row.subject_key,
                    subject_name=row.subject_name,
                    support_score=support_score,
                    momentum_score=momentum_score,
                    candidate_score=candidate_score,
                    candidate_level=level,
                    evidence_rules=evidence,
                )
            )

        candidates.sort(key=lambda c: c.candidate_score, reverse=True)
        return candidates
