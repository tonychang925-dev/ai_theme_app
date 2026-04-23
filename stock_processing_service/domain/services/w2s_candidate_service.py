from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

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
    candidate_source: str
    evidence_rules: list[str]


class W2SCandidateService:
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
    def _grade_base(strong_grade: str) -> Decimal:
        grade = (strong_grade or "").upper()
        if grade == "S":
            return Decimal("95")
        if grade == "A":
            return Decimal("85")
        if grade == "B":
            return Decimal("75")
        return Decimal("50")

    @staticmethod
    def _weakness_valid_score(pct_chg: Decimal) -> Decimal:
        if Decimal("-5") <= pct_chg <= Decimal("-1"):
            return Decimal("90")
        if Decimal("-1") < pct_chg <= Decimal("1"):
            return Decimal("70")
        if Decimal("1") < pct_chg <= Decimal("3"):
            return Decimal("50")
        if Decimal("3") < pct_chg <= Decimal("6"):
            return Decimal("30")
        if pct_chg > Decimal("6"):
            return Decimal("15")
        if Decimal("-8") <= pct_chg < Decimal("-5"):
            return Decimal("45")
        return Decimal("20")

    def _mainline_context_score(self, rank: int, role_tags: dict[str, Any]) -> Decimal:
        rank_score = Decimal("100") / Decimal(str(max(rank, 1)))
        is_leader = bool(role_tags.get("is_leader"))
        is_front_row = bool(role_tags.get("is_front_row_core"))
        leader_bonus = Decimal("15") if is_leader else Decimal("0")
        front_row_bonus = Decimal("10") if is_front_row else Decimal("0")
        return min(Decimal("100"), rank_score * Decimal("0.7") + leader_bonus + front_row_bonus)

    def _strong_gene_score(
        self,
        watch_score: Decimal,
        strong_grade: str,
        prior7_limitup_days: int,
        prior7_strong_days: int,
    ) -> Decimal:
        grade_base = self._grade_base(strong_grade)
        history_score = min(
            Decimal("100"),
            Decimal(str(prior7_limitup_days * 20 + prior7_strong_days * 12)),
        )
        return min(
            Decimal("100"),
            watch_score * Decimal("0.6") + grade_base * Decimal("0.3") + history_score * Decimal("0.1"),
        )

    def _support_hit_score(
        self,
        support_score: Decimal,
        support_type: str,
        support_refs: list[str],
    ) -> Decimal:
        refs_bonus = Decimal(str(min(len(support_refs), 5) * 5))
        support_type_bonus = Decimal("0")
        if support_type in {"previous_low", "prev_low_support", "ma_support", "platform_support"}:
            support_type_bonus = Decimal("5")
        return min(Decimal("100"), support_score * Decimal("0.85") + refs_bonus + support_type_bonus)

    @staticmethod
    def _repair_or_takeover_score(prior_state: str, role_tags: dict[str, Any]) -> Decimal:
        state = (prior_state or "").lower()
        base = Decimal("50")
        if state == "repair":
            base = Decimal("85")
        elif state == "fade_watch":
            base = Decimal("75")
        elif state == "divergence":
            base = Decimal("55")

        if bool(role_tags.get("is_leader")):
            base += Decimal("8")
        if str(role_tags.get("watch_tier", "")).upper() in {"S", "A"}:
            base += Decimal("5")
        return min(Decimal("100"), base)

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
            source = str((row.metadata or {}).get("candidate_source", "pool_unknown"))
            if source != "strong_watch_pool":
                continue
            bar = bar_by_stock.get(row.stock_id)
            if bar is None:
                continue

            metadata = row.metadata or {}
            role_tags = metadata.get("role_tags") if isinstance(metadata.get("role_tags"), dict) else {}
            support_refs = metadata.get("support_refs")
            if not isinstance(support_refs, list):
                support_refs = []
            strong_grade = str(metadata.get("strong_grade") or "B")
            watch_score = self._d(metadata.get("watch_score"), default="60")
            support_score = self._d(metadata.get("support_score"), default="50")
            support_type = str(metadata.get("support_type") or "")
            prior7_limitup_days = int(metadata.get("prior7_limitup_days") or 0)
            prior7_strong_days = int(metadata.get("prior7_strong_days") or 0)

            rank = row.pool_rank if row.pool_rank is not None else 999
            mainline_context_score = self._mainline_context_score(rank, role_tags)
            strong_gene_score = self._strong_gene_score(
                watch_score,
                strong_grade,
                prior7_limitup_days,
                prior7_strong_days,
            )
            support_hit_score = self._support_hit_score(
                support_score=support_score,
                support_type=support_type,
                support_refs=support_refs,
            )
            weakness_valid_score = self._weakness_valid_score(bar.pct_chg)

            prior_state = ""
            prior = prior_by_stock.get(row.stock_id)
            if prior:
                prior_state = str(prior.payload.get("final_cycle_state", ""))
            repair_or_takeover_score = self._repair_or_takeover_score(prior_state, role_tags)

            candidate_score = (
                mainline_context_score * Decimal("0.10")
                + strong_gene_score * Decimal("0.20")
                + support_hit_score * Decimal("0.35")
                + repair_or_takeover_score * Decimal("0.10")
                + weakness_valid_score * Decimal("0.25")
            )
            overheat_penalty = max(Decimal("0"), bar.pct_chg) * Decimal("6")
            candidate_score = max(Decimal("0"), candidate_score - overheat_penalty)

            hard_reject = (
                strong_grade.upper() not in {"S", "A", "B"}
                or support_hit_score < Decimal("45")
                or watch_score < Decimal("45")
            )
            if hard_reject:
                continue
            if (
                candidate_score >= Decimal("66")
                and support_hit_score >= Decimal("60")
                and strong_gene_score >= Decimal("58")
                and weakness_valid_score >= Decimal("50")
            ):
                level = "formal"
            elif candidate_score >= Decimal("52"):
                level = "observe_only"
            else:
                continue

            evidence = [
                f"pool_rank={row.pool_rank}",
                f"pct_chg={bar.pct_chg}",
                f"prior_state={prior_state or 'unknown'}",
                f"watch_score={watch_score}",
                f"strong_grade={strong_grade}",
                f"support_score={support_score}",
                f"support_type={support_type or 'unknown'}",
                f"role_tags={role_tags}",
                f"prior7_limitup_days={prior7_limitup_days}",
                f"prior7_strong_days={prior7_strong_days}",
                f"mainline_context_score={mainline_context_score}",
                f"strong_gene_score={strong_gene_score}",
                f"support_hit_score={support_hit_score}",
                f"repair_or_takeover_score={repair_or_takeover_score}",
                f"weakness_valid_score={weakness_valid_score}",
                f"overheat_penalty={overheat_penalty}",
            ]
            candidates.append(
                W2SCandidate(
                    trade_date=str(row.trade_date),
                    stock_id=row.stock_id,
                    stock_name=row.stock_name or bar.stock_name,
                    subject_key=row.subject_key,
                    subject_name=row.subject_name,
                    support_score=support_hit_score,
                    momentum_score=weakness_valid_score,
                    candidate_score=candidate_score,
                    candidate_level=level,
                    candidate_source=source,
                    evidence_rules=evidence,
                )
            )

        candidates.sort(key=lambda c: c.candidate_score, reverse=True)
        return candidates
