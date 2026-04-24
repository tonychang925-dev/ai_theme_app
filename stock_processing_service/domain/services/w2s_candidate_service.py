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
    formal_bias: bool = False
    overheated: bool = False
    formal_fail_reason: str | None = None
    reject_reason: str | None = None
    support_type: str = ""
    gap_hit: bool = False
    gap_hit_mode: str = "miss"
    gap_source: str = ""
    gap_structure_bonus: Decimal = Decimal("0")
    gap_repair_bonus: Decimal = Decimal("0")
    repair_or_takeover_score: Decimal = Decimal("0")
    weakness_valid_score: Decimal = Decimal("0")


class W2SCandidateService:
    MAX_CANDIDATES = 10
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
        if grade == "B_KEEP":
            return Decimal("68")
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
    def _gap_structure_bonus(support_type: str, gap_hit: bool, gap_hit_mode: str) -> Decimal:
        if support_type != "gap_support" or not gap_hit:
            return Decimal("0")
        if gap_hit_mode == "strict":
            return Decimal("10")
        if gap_hit_mode == "soft":
            return Decimal("6")
        return Decimal("0")

    @staticmethod
    def _gap_repair_bonus(
        support_type: str,
        gap_hit: bool,
        repair_or_takeover_score: Decimal,
    ) -> Decimal:
        if support_type == "gap_support" and gap_hit and repair_or_takeover_score >= Decimal("50"):
            return Decimal("4")
        return Decimal("0")

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

    @staticmethod
    def _in_range(value: Decimal, low: str, high: str) -> bool:
        return Decimal(low) <= value <= Decimal(high)

    def _prior7_features(
        self,
        *,
        stock_id: str,
        prior_rows: list[PriorSnapshotDTO],
        metadata: dict[str, Any],
    ) -> tuple[int, int, str]:
        m_limit = metadata.get("prior7_limitup_days")
        m_strong = metadata.get("prior7_strong_days")
        if m_limit is not None or m_strong is not None:
            return int(m_limit or 0), int(m_strong or 0), "metadata"

        rows = [r for r in prior_rows if r.stock_id == stock_id]
        limitup_days = 0
        strong_days = 0
        for r in rows:
            pct_raw = (r.payload or {}).get("pct_chg")
            pct = self._d(pct_raw, default="0")
            if pct >= Decimal("9.5"):
                limitup_days += 1
            if pct >= Decimal("5"):
                strong_days += 1
        return limitup_days, strong_days, "prior_snapshots"

    def explain_candidate(
        self,
        *,
        row: SubjectStockPoolDTO,
        bar: StockBarDTO | None,
        prior: PriorSnapshotDTO | None,
        prior_rows: list[PriorSnapshotDTO] | None = None,
    ) -> dict[str, Any]:
        source = str((row.metadata or {}).get("candidate_source", "pool_unknown"))
        metadata = row.metadata or {}
        role_tags = metadata.get("role_tags") if isinstance(metadata.get("role_tags"), dict) else {}
        support_refs = metadata.get("support_refs") if isinstance(metadata.get("support_refs"), list) else []
        strong_grade = str(metadata.get("strong_grade") or "B")
        watch_status = str(metadata.get("watch_status") or "")
        kept_because = str(metadata.get("kept_because") or "")
        watch_score = self._d(metadata.get("watch_score"), default="60")
        support_score = self._d(metadata.get("support_score"), default="50")
        support_type = str(metadata.get("support_type") or "")
        support_count = int(metadata.get("support_count") or 0)
        support_combined_strength = self._d(metadata.get("support_combined_strength"), default="0")
        gap_hit = bool(metadata.get("gap_hit") or False)
        gap_hit_mode = str(metadata.get("gap_hit_mode") or "miss")
        gap_source = str(metadata.get("gap_source") or "")
        gap_level = self._d(metadata.get("gap_level"), default="0")
        gap_distance_pct = self._d(metadata.get("gap_distance_pct"), default="999")
        prior7_limitup_days, prior7_strong_days, prior7_source = self._prior7_features(
            stock_id=row.stock_id,
            prior_rows=prior_rows or [],
            metadata=metadata,
        )

        prior_state = ""
        if prior:
            prior_state = str(prior.payload.get("final_cycle_state", ""))

        if bar is None:
            return {
                "candidate_source": source,
                "candidate_level": "reject",
                "reject_reason": "missing_bar",
            }

        rank = row.pool_rank if row.pool_rank is not None else 999
        pct_chg = bar.pct_chg
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
        repair_or_takeover_score = self._repair_or_takeover_score(prior_state, role_tags)
        weakness_valid_score = self._weakness_valid_score(pct_chg)
        overheat_penalty = max(Decimal("0"), pct_chg) * Decimal("6")

        prior7_bonus = Decimal("0")
        if prior7_limitup_days >= 1:
            prior7_bonus += Decimal("5")
        if prior7_strong_days >= 2:
            prior7_bonus += Decimal("3")

        w2s_pathway_bonus = Decimal("0")
        if (
            watch_status in {"weakening", "weakening_keep"}
            and support_type in {"previous_low", "prev_low_support", "platform_support"}
            and support_hit_score >= Decimal("70")
            and weakness_valid_score >= Decimal("60")
        ):
            w2s_pathway_bonus = Decimal("10")
        formal_w2s_override = (
            watch_status in {"weakening", "weakening_keep"}
            and support_type in {"previous_low", "prev_low_support", "platform_support"}
            and support_hit_score >= Decimal("75")
            and weakness_valid_score >= Decimal("60")
        )

        gap_structure_bonus = self._gap_structure_bonus(
            support_type=support_type,
            gap_hit=gap_hit,
            gap_hit_mode=gap_hit_mode,
        )
        gap_repair_bonus = self._gap_repair_bonus(
            support_type=support_type,
            gap_hit=gap_hit,
            repair_or_takeover_score=repair_or_takeover_score,
        )
        gap_formal_bias_bonus = Decimal("0")
        if formal_w2s_override and support_type == "gap_support" and gap_hit:
            gap_formal_bias_bonus = Decimal("3")

        raw_score = (
            mainline_context_score * Decimal("0.08")
            + strong_gene_score * Decimal("0.18")
            + support_hit_score * Decimal("0.34")
            + repair_or_takeover_score * Decimal("0.18")
            + weakness_valid_score * Decimal("0.22")
        )
        candidate_score = max(
            Decimal("0"),
            min(
                Decimal("100"),
                raw_score
                - overheat_penalty
                + prior7_bonus
                + w2s_pathway_bonus
                + gap_structure_bonus
                + gap_repair_bonus
                + gap_formal_bias_bonus,
            ),
        )

        formal_day_gate = self._in_range(pct_chg, "-6", "1.5")
        observe_day_gate = self._in_range(pct_chg, "-8", "3")
        prior7_formal_gate = prior7_limitup_days >= 1 or prior7_strong_days >= 2
        prior7_soft_pass = True

        rank_overheat_gate = rank <= 2 and pct_chg > Decimal("3")
        leader_overheat_gate = bool(role_tags.get("is_leader")) and pct_chg > Decimal("2.5")
        tier_overheat_gate = str(role_tags.get("watch_tier", "")).upper() in {"S", "A"} and pct_chg > Decimal("4")
        overheat_hard_gate = rank_overheat_gate or leader_overheat_gate or tier_overheat_gate
        overheated = overheat_hard_gate

        extreme_invalid = (
            pct_chg < Decimal("-8")
            or pct_chg > Decimal("6")
            or (bool(role_tags.get("is_leader")) and pct_chg > Decimal("5"))
        )
        hard_reject = (
            strong_grade.upper() not in {"S", "A", "B", "B_KEEP"}
            or watch_status == "removed"
            or extreme_invalid
            or (support_hit_score < Decimal("45") and repair_or_takeover_score < Decimal("45") and strong_gene_score < Decimal("45"))
        )

        level = "reject"
        reject_reason = ""
        formal_fail_reason = ""
        if hard_reject:
            reject_reason = "hard_reject"
        else:
            formal_ok = (
                candidate_score >= Decimal("60")
                and support_hit_score >= Decimal("60")
                and repair_or_takeover_score >= Decimal("50")
                and formal_day_gate
                and not overheat_hard_gate
            )
            if formal_w2s_override and candidate_score >= Decimal("60") and formal_day_gate and not overheat_hard_gate:
                formal_ok = True
            if formal_ok:
                level = "formal"
            elif observe_day_gate and candidate_score >= Decimal("48"):
                level = "observe_only"
                if overheat_hard_gate:
                    formal_fail_reason = "overheated_front_row"
                elif not formal_day_gate:
                    formal_fail_reason = "formal_day_gate_failed"
                elif support_hit_score < Decimal("60"):
                    formal_fail_reason = "support_too_low"
                elif repair_or_takeover_score < Decimal("55"):
                    formal_fail_reason = "repair_score_too_low"
                else:
                    formal_fail_reason = "candidate_score_below_formal"
            else:
                reject_reason = "score_below_observe_threshold"
                if not observe_day_gate:
                    formal_fail_reason = "observe_day_gate_failed"
                else:
                    formal_fail_reason = "candidate_score_below_observe"

        return {
            "candidate_source": source,
            "pool_rank": rank,
            "pct_chg": str(pct_chg),
            "prior_state": prior_state or "unknown",
            "watch_score": str(watch_score),
            "strong_grade": strong_grade,
            "support_score": str(support_score),
            "support_type": support_type or "unknown",
            "support_count": support_count,
            "support_combined_strength": str(support_combined_strength),
            "gap_hit": gap_hit,
            "gap_hit_mode": gap_hit_mode,
            "gap_source": gap_source,
            "gap_level": str(gap_level),
            "gap_distance_pct": str(gap_distance_pct),
            "role_tags": role_tags,
            "prior7_limitup_days": prior7_limitup_days,
            "prior7_strong_days": prior7_strong_days,
            "prior7_source": prior7_source,
            "mainline_context_score": str(mainline_context_score),
            "strong_gene_score": str(strong_gene_score),
            "support_hit_score": str(support_hit_score),
            "repair_or_takeover_score": str(repair_or_takeover_score),
            "weakness_valid_score": str(weakness_valid_score),
            "overheat_penalty": str(overheat_penalty),
            "candidate_score": str(candidate_score),
            "formal_day_gate": formal_day_gate,
            "observe_day_gate": observe_day_gate,
            "prior7_formal_gate": prior7_formal_gate,
            "prior7_soft_pass": prior7_soft_pass,
            "formal_w2s_override": formal_w2s_override,
            "prior7_bonus": str(prior7_bonus),
            "w2s_pathway_bonus": str(w2s_pathway_bonus),
            "gap_structure_bonus": str(gap_structure_bonus),
            "gap_repair_bonus": str(gap_repair_bonus),
            "gap_formal_bias_bonus": str(gap_formal_bias_bonus),
            "overheat_hard_gate": overheat_hard_gate,
            "overheated": overheated,
            "candidate_level": level,
            "reject_reason": reject_reason,
            "formal_fail_reason": formal_fail_reason,
            "watch_status": watch_status or "unknown",
            "kept_because": kept_because,
        }

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
            prior = prior_by_stock.get(row.stock_id)
            explain = self.explain_candidate(
                row=row,
                bar=bar,
                prior=prior,
                prior_rows=prior_rows,
            )
            if explain.get("candidate_source") != "strong_watch_pool":
                continue
            level = str(explain.get("candidate_level") or "reject")
            if level not in {"formal", "observe_only"}:
                continue

            evidence = [
                f"pool_rank={explain['pool_rank']}",
                f"pct_chg={explain['pct_chg']}",
                f"prior_state={explain['prior_state']}",
                f"watch_score={explain['watch_score']}",
                f"strong_grade={explain['strong_grade']}",
                f"support_score={explain['support_score']}",
                f"support_type={explain['support_type']}",
                f"support_count={explain.get('support_count', 0)}",
                f"support_combined_strength={explain.get('support_combined_strength', '0')}",
                f"gap_hit={explain.get('gap_hit', False)}",
                f"gap_hit_mode={explain.get('gap_hit_mode', 'miss')}",
                f"gap_source={explain.get('gap_source', '')}",
                f"gap_level={explain.get('gap_level', '0')}",
                f"gap_distance_pct={explain.get('gap_distance_pct', '999')}",
                f"gap_structure_bonus={explain.get('gap_structure_bonus', '0')}",
                f"gap_repair_bonus={explain.get('gap_repair_bonus', '0')}",
                f"gap_formal_bias_bonus={explain.get('gap_formal_bias_bonus', '0')}",
                f"role_tags={explain['role_tags']}",
                f"prior7_limitup_days={explain['prior7_limitup_days']}",
                f"prior7_strong_days={explain['prior7_strong_days']}",
                f"mainline_context_score={explain['mainline_context_score']}",
                f"strong_gene_score={explain['strong_gene_score']}",
                f"support_hit_score={explain['support_hit_score']}",
                f"repair_or_takeover_score={explain['repair_or_takeover_score']}",
                f"weakness_valid_score={explain['weakness_valid_score']}",
                f"overheat_penalty={explain['overheat_penalty']}",
                f"prior7_bonus={explain['prior7_bonus']}",
                f"formal_bias={explain['formal_w2s_override']}",
                f"overheated={explain['overheated']}",
            ]
            if explain.get("reject_reason"):
                evidence.append(f"candidate_note={explain['reject_reason']}")
            if explain.get("formal_fail_reason"):
                evidence.append(f"formal_fail_reason={explain['formal_fail_reason']}")

            candidate = W2SCandidate(
                trade_date=str(row.trade_date),
                stock_id=row.stock_id,
                stock_name=row.stock_name or (bar.stock_name if bar else ""),
                subject_key=row.subject_key,
                subject_name=row.subject_name,
                support_score=self._d(explain.get("support_hit_score")),
                momentum_score=self._d(explain.get("weakness_valid_score")),
                candidate_score=self._d(explain.get("candidate_score")),
                candidate_level=level,
                candidate_source=str(explain.get("candidate_source", "")),
                evidence_rules=evidence,
                formal_bias=bool(explain.get("formal_w2s_override")),
                overheated=bool(explain.get("overheated")),
                formal_fail_reason=str(explain.get("formal_fail_reason") or "") or None,
                reject_reason=str(explain.get("reject_reason") or "") or None,
                support_type=str(explain.get("support_type") or ""),
                gap_hit=bool(explain.get("gap_hit")),
                gap_hit_mode=str(explain.get("gap_hit_mode") or "miss"),
                gap_source=str(explain.get("gap_source") or ""),
                gap_structure_bonus=self._d(explain.get("gap_structure_bonus")),
                gap_repair_bonus=self._d(explain.get("gap_repair_bonus")),
                repair_or_takeover_score=self._d(explain.get("repair_or_takeover_score")),
                weakness_valid_score=self._d(explain.get("weakness_valid_score")),
            )
            candidates.append(candidate)

        def _formal_support_priority(support_type: str) -> int:
            st = (support_type or "").strip().lower()
            if st in {"previous_low", "prev_low_support"}:
                return 0
            if st == "platform_support":
                return 1
            if st == "ma_support":
                return 2
            return 3

        formal_candidates = [c for c in candidates if c.candidate_level == "formal"]
        observe_candidates = [c for c in candidates if c.candidate_level == "observe_only"]

        def _gap_priority(c: W2SCandidate) -> int:
            if c.support_type == "gap_support" and c.gap_hit:
                if c.gap_hit_mode == "strict":
                    return 0
                if c.gap_hit_mode == "soft":
                    return 1
            return 2

        def _formal_key(c: W2SCandidate) -> tuple[int, int, Decimal, Decimal, Decimal, Decimal]:
            return (
                _gap_priority(c),
                0 if c.formal_bias else 1,
                -c.repair_or_takeover_score,
                -c.weakness_valid_score,
                -c.candidate_score,
                _formal_support_priority(c.support_type),
            )

        def _observe_key(c: W2SCandidate) -> tuple[Decimal, Decimal, Decimal]:
            return (
                -c.candidate_score,
                -c.support_score,
                -c.weakness_valid_score,
            )

        formal_candidates.sort(key=_formal_key)
        observe_candidates.sort(key=_observe_key)
        return (formal_candidates + observe_candidates)[: self.MAX_CANDIDATES]
