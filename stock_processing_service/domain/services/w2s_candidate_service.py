from __future__ import annotations

import os
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
    transition_type: str = ""
    transition_confidence: Decimal = Decimal("0")
    trigger_flags: list[str] | None = None


class W2SCandidateService:
    MAX_CANDIDATES = 20

    def __init__(self) -> None:
        self._observe_candidates: list[W2SCandidate] = []

    @property
    def observe_candidates(self) -> list[W2SCandidate]:
        return list(self._observe_candidates)
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
        if support_type == "gap_support":
            support_type_bonus = Decimal("8")
        elif support_type in {"previous_low", "prev_low_support", "platform_support"}:
            support_type_bonus = Decimal("5")
        elif support_type == "ma_support":
            support_type_bonus = Decimal("3")
        return min(Decimal("100"), support_score * Decimal("0.85") + refs_bonus + support_type_bonus)

    @staticmethod
    def _support_strength(pct_chg: Decimal, prev_day_pct: Decimal, support_type: str) -> Decimal:
        base = Decimal("20") if support_type == "none" else Decimal("45")
        if prev_day_pct <= Decimal("-4"):
            base += Decimal("15")
        if Decimal("-1.5") <= pct_chg <= Decimal("2.5"):
            base += Decimal("10")
        return min(base, Decimal("95"))

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

    @staticmethod
    def _weekly_midterm_gate(metadata: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        weekly_data_sufficient = bool(metadata.get("weekly_data_sufficient") or False)
        weekly_trend_up = bool(metadata.get("weekly_trend_up") or False)
        weekly_filter_pass = bool(metadata.get("weekly_filter_pass") or False)
        weekly_high_fall_flag = bool(metadata.get("weekly_high_fall_flag") or False)
        weekly_position_pct = metadata.get("weekly_position_pct")
        weekly_pullback_pct = metadata.get("weekly_pullback_pct")
        if not weekly_data_sufficient:
            # Backward-compatible default: lack of weekly data should not block
            # candidate promotion in baseline pipelines/tests.
            return True, {
                "passed": True,
                "reason": "weekly_data_insufficient_bypass",
                "weekly_data_sufficient": weekly_data_sufficient,
                "weekly_trend_up": weekly_trend_up,
                "weekly_filter_pass": weekly_filter_pass,
                "weekly_high_fall_flag": weekly_high_fall_flag,
                "weekly_position_pct": str(weekly_position_pct if weekly_position_pct is not None else ""),
                "weekly_pullback_pct": str(weekly_pullback_pct if weekly_pullback_pct is not None else ""),
            }
        passed = weekly_filter_pass and weekly_trend_up and (not weekly_high_fall_flag)
        return passed, {
            "passed": passed,
            "reason": "weekly_gate_passed" if passed else "weekly_gate_failed",
            "weekly_data_sufficient": weekly_data_sufficient,
            "weekly_trend_up": weekly_trend_up,
            "weekly_filter_pass": weekly_filter_pass,
            "weekly_high_fall_flag": weekly_high_fall_flag,
            "weekly_position_pct": str(weekly_position_pct if weekly_position_pct is not None else ""),
            "weekly_pullback_pct": str(weekly_pullback_pct if weekly_pullback_pct is not None else ""),
        }

    @staticmethod
    def _legacy_watch_status_pass(watch_status: str) -> bool:
        return (watch_status or "").strip().lower() in {"active", "weakening", "weakening_keep"}

    @staticmethod
    def _legacy_strong_history_gate(
        *,
        prior7_limitup_days: int,
        prior7_strong_days: int,
        two_board_entry: bool,
    ) -> tuple[bool, str]:
        # Old-chain semantics:
        # 1) hard gene + strong history (both required), OR
        # 2) two-board bypass (already vetted in Layer C).
        if two_board_entry:
            return True, "two_board_bypass"
        if prior7_limitup_days >= 1 and prior7_strong_days >= 1:
            return True, "prior7_dual_pass"
        return False, "prior7_dual_fail"

    @staticmethod
    def _day_weak_score(pct_chg: Decimal) -> Decimal:
        if pct_chg < Decimal("-4"):
            return Decimal("20")
        if pct_chg < Decimal("-2"):
            return Decimal("16")
        if pct_chg < Decimal("-1"):
            return Decimal("10")
        if pct_chg < Decimal("0"):
            return Decimal("6")
        return Decimal("0")

    @staticmethod
    def _classify_weak_type(pct_chg: float, prev_day_pct: float, prev_day_limit_up: bool) -> tuple[str, float]:
        if prev_day_limit_up and pct_chg < 0:
            return "bad_limit_up", min(100.0, abs(pct_chg) * 12.0 + 20.0)
        if pct_chg <= -5.0:
            return "big_negative_line", min(100.0, abs(pct_chg) * 10.0)
        if -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
            return "upper_shadow", 55.0
        if pct_chg <= -1.0:
            return "high_open_low_close", min(100.0, abs(pct_chg) * 8.0 + 10.0)
        return "fake_break", 40.0

    @staticmethod
    def _prev_day_weak_score(prev_day_pct: Decimal) -> Decimal:
        if prev_day_pct < Decimal("-3"):
            return Decimal("10")
        if prev_day_pct < Decimal("-1.5"):
            return Decimal("8")
        if prev_day_pct < Decimal("0"):
            return Decimal("5")
        return Decimal("0")

    @staticmethod
    def _fade_watch_penalty(*, fade_watch: bool, mainline_strength_score: Decimal) -> Decimal:
        if not fade_watch:
            return Decimal("0")
        if mainline_strength_score >= Decimal("75"):
            return Decimal("4")
        if mainline_strength_score >= Decimal("60"):
            return Decimal("8")
        return Decimal("12")

    def _candidate_score(
        self,
        *,
        is_leader: bool,
        limit_up: bool,
        recent_limit_up_count: int,
        rank_order: int,
        stage: str,
        weak_intensity: Decimal,
        support_strength: Decimal,
        day_weak_score: Decimal = Decimal("0"),
        prev_day_weak_score: Decimal = Decimal("0"),
        mainline_strength_score: Decimal = Decimal("0"),
        fade_watch: bool = False,
    ) -> Decimal:
        score = Decimal("45")
        if is_leader:
            score += Decimal("18")
        if limit_up:
            score += Decimal("10")
        score += min(Decimal(str(recent_limit_up_count)) * Decimal("4"), Decimal("12"))
        if rank_order <= 3:
            score += Decimal("8")
        if stage in {"rebound", "fermentation", "回流", "发酵", "启动"}:
            score += Decimal("8")
        score += min(Decimal(str(weak_intensity)) * Decimal("0.08"), Decimal("8"))
        score += min(support_strength * Decimal("0.1"), Decimal("9"))
        score += day_weak_score + prev_day_weak_score
        score += min(mainline_strength_score * Decimal("0.08"), Decimal("8"))
        score -= self._fade_watch_penalty(fade_watch=fade_watch, mainline_strength_score=mainline_strength_score)
        return max(Decimal("0"), min(score, Decimal("100")))

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
        transition_type = str(metadata.get("transition_type") or "")
        transition_confidence = self._d(metadata.get("transition_confidence"), default="0")
        trigger_flags = list(metadata.get("trigger_flags") or [])
        two_board_entry = bool(role_tags.get("two_board_entry") or False)
        limit_up = bool(metadata.get("limit_up") or role_tags.get("limit_up") or False)
        prior7_limitup_days, prior7_strong_days, prior7_source = self._prior7_features(
            stock_id=row.stock_id,
            prior_rows=prior_rows or [],
            metadata=metadata,
        )
        weekly_gate_passed, weekly_gate_diag = self._weekly_midterm_gate(metadata)

        prior_state = ""
        prior_state_unknown = False
        if prior:
            prior_state = str(prior.payload.get("final_cycle_state", ""))
        if not prior_state or prior_state.strip().lower() in {"", "unknown", "none"}:
            prior_state_unknown = True
            prior_state = "unknown"
        prev_day_pct = self._d((prior.payload or {}).get("pct_chg") if prior else None, default="0")
        prev_day_limit_up = bool((prior.payload or {}).get("limit_up") if prior else False) or prev_day_pct >= Decimal("9.5")

        if bar is None:
            return {
                "candidate_source": source,
                "candidate_level": "reject",
                "reject_reason": "missing_bar",
            }

        rank = row.pool_rank if row.pool_rank is not None else 999
        pct_chg = bar.pct_chg
        mainline_context_score = self._mainline_context_score(rank, role_tags)
        weak_type, weak_intensity = self._classify_weak_type(float(pct_chg), float(prev_day_pct), prev_day_limit_up)
        day_weak_score = self._day_weak_score(pct_chg)
        prev_day_weak_score = self._prev_day_weak_score(prev_day_pct)
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
        support_strength = self._support_strength(pct_chg, prev_day_pct, support_type)
        repair_or_takeover_score = self._repair_or_takeover_score(prior_state, role_tags)
        weakness_valid_score = self._weakness_valid_score(pct_chg)
        overheat_penalty = max(Decimal("0"), pct_chg) * Decimal("6")

        prior7_bonus = Decimal("0")
        if prior7_limitup_days >= 1:
            prior7_bonus += Decimal("5")
        if prior7_strong_days >= 2:
            prior7_bonus += Decimal("3")

        gap_structure_bonus = self._gap_structure_bonus(
            support_type=support_type,
            gap_hit=gap_hit,
            gap_hit_mode=gap_hit_mode,
        )
        candidate_score = self._candidate_score(
            is_leader=bool(role_tags.get("is_leader")),
            limit_up=limit_up,
            recent_limit_up_count=int(metadata.get("recent_limit_up_count") or 0),
            rank_order=rank,
            stage=prior_state,
            weak_intensity=weak_intensity,
            support_strength=support_strength,
            day_weak_score=day_weak_score,
            prev_day_weak_score=prev_day_weak_score,
            mainline_strength_score=mainline_context_score,
            fade_watch=bool(metadata.get("fade_watch") or role_tags.get("fade_watch") or False),
        )
        legacy_watch_status_pass = self._legacy_watch_status_pass(watch_status)
        legacy_strong_history_pass, legacy_strong_history_reason = self._legacy_strong_history_gate(
            prior7_limitup_days=prior7_limitup_days,
            prior7_strong_days=prior7_strong_days,
            two_board_entry=two_board_entry,
        )

        rank_overheat_gate = rank <= 2 and pct_chg > Decimal("3")
        leader_overheat_gate = bool(role_tags.get("is_leader")) and pct_chg > Decimal("2.5")
        tier_overheat_gate = str(role_tags.get("watch_tier", "")).upper() in {"S", "A"} and pct_chg > Decimal("4")
        overheat_hard_gate = rank_overheat_gate or leader_overheat_gate or tier_overheat_gate
        overheated = overheat_hard_gate

        # Hard reject: only structure-destroyed or zero-gene candidates.
        # Legacy watch_status / strong_history gates removed.
        hard_reject = (
            support_hit_score < Decimal("35")
            and repair_or_takeover_score < Decimal("35")
            and strong_gene_score < Decimal("35")
        )

        risk_flags: list[str] = []
        _prev_day_weak_soft_pass = False

        level = "reject"
        reject_reason = ""
        if hard_reject:
            reject_reason = "hard_reject"
        else:
            support_strength = support_hit_score
            day_weak_score = self._day_weak_score(pct_chg)
            prev_day_weak_score = self._prev_day_weak_score(prev_day_pct)
            strong_background = bool(role_tags.get("is_leader")) or limit_up or int(metadata.get("recent_limit_up_count") or 0) >= 2 or rank <= 3

            # ── D layer: diagnose, don't re-judge ──
            # prior_state=unknown is a soft risk (data missing), not a hard reject.
            # D_LAYER_ALLOW_UNKNOWN_PRIOR_STATE (default 1): soft-pass prev_day_weak gate
            # when prior_state is unknown, rather than falsely equating "unknown" to "prev_day_not_weak".
            _allow_unknown_prior = os.environ.get("D_LAYER_ALLOW_UNKNOWN_PRIOR_STATE", "1") == "1"
            _prev_day_weak_ok = prev_day_weak_score >= Decimal("2")
            _prev_day_weak_soft_pass = False

            if prior_state_unknown and _allow_unknown_prior:
                _prev_day_weak_ok = True
                _prev_day_weak_soft_pass = True
                risk_flags.append("prior_state_unknown")

            formal_ok = (
                support_strength >= Decimal("45")
                and strong_background
                and day_weak_score >= Decimal("4")
                and _prev_day_weak_ok
            )
            observe_only_ok = (
                support_strength >= Decimal("60")
                and day_weak_score >= Decimal("3")
                and _prev_day_weak_ok
            )
            if formal_ok:
                level = "formal"
            elif observe_only_ok:
                level = "observe_only"
            else:
                reject_reason = "score_below_observe_threshold"

        return {
            "candidate_source": source,
            "pool_rank": rank,
            "pct_chg": str(pct_chg),
            "prior_state": prior_state or "unknown",
            "watch_score": str(watch_score),
            "strong_grade": strong_grade,
            "support_score": str(support_score),
            "support_type": support_type or "unknown",
            "support_strength": str(support_strength),
            "support_count": support_count,
            "support_combined_strength": str(support_combined_strength),
            "gap_hit": gap_hit,
            "gap_hit_mode": gap_hit_mode,
            "gap_source": gap_source,
            "gap_level": str(gap_level),
            "gap_distance_pct": str(gap_distance_pct),
            "transition_type": transition_type,
            "transition_confidence": str(transition_confidence),
            "trigger_flags": trigger_flags,
            "role_tags": role_tags,
            "prior7_limitup_days": prior7_limitup_days,
            "prior7_strong_days": prior7_strong_days,
            "prior7_source": prior7_source,
            "mainline_context_score": str(mainline_context_score),
            "strong_gene_score": str(strong_gene_score),
            "support_hit_score": str(support_hit_score),
            "repair_or_takeover_score": str(repair_or_takeover_score),
            "weakness_valid_score": str(weakness_valid_score),
            "overheat_penalty": str(self._fade_watch_penalty(fade_watch=bool(metadata.get("fade_watch") or role_tags.get("fade_watch") or False), mainline_strength_score=mainline_context_score)),
            "candidate_score": str(candidate_score),
            "weekly_midterm_gate_passed": weekly_gate_passed,
            "weekly_midterm_gate_reason": str(weekly_gate_diag.get("reason") or ""),
            "legacy_watch_status_pass": legacy_watch_status_pass,
            "legacy_strong_history_pass": legacy_strong_history_pass,
            "legacy_strong_history_reason": legacy_strong_history_reason,
            "two_board_entry": two_board_entry,
            "prior7_bonus": "0",
            "gap_structure_bonus": "0",
            "gap_repair_bonus": "0",
            "gap_formal_bias_bonus": "0",
            "overheat_hard_gate": overheat_hard_gate,
            "overheated": overheated,
            "candidate_level": level,
            "reject_reason": reject_reason,
            "watch_status": watch_status or "unknown",
            "kept_because": kept_because,
            "risk_flags": risk_flags,
            "prior_state_unknown": prior_state_unknown,
            "prev_day_weak_soft_pass": _prev_day_weak_soft_pass,
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
                f"support_strength={explain.get('support_strength', '0')}",
                f"support_count={explain.get('support_count', 0)}",
                f"support_combined_strength={explain.get('support_combined_strength', '0')}",
                f"gap_hit={explain.get('gap_hit', False)}",
                f"gap_hit_mode={explain.get('gap_hit_mode', 'miss')}",
                f"gap_source={explain.get('gap_source', '')}",
                f"gap_level={explain.get('gap_level', '0')}",
                f"gap_distance_pct={explain.get('gap_distance_pct', '999')}",
                f"transition_type={explain.get('transition_type', '')}",
                f"transition_confidence={explain.get('transition_confidence', '0')}",
                f"trigger_flags={explain.get('trigger_flags', [])}",
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
                f"watch_status={explain.get('watch_status', 'unknown')}",
                f"weekly_midterm_gate_passed={explain.get('weekly_midterm_gate_passed', True)}",
                f"weekly_midterm_gate_reason={explain.get('weekly_midterm_gate_reason', '')}",
                f"overheated={explain['overheated']}",
            ]
            if explain.get("reject_reason"):
                evidence.append(f"candidate_note={explain['reject_reason']}")

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
                formal_bias=False,
                overheated=bool(explain.get("overheated")),
                reject_reason=str(explain.get("reject_reason") or "") or None,
                support_type=str(explain.get("support_type") or ""),
                gap_hit=bool(explain.get("gap_hit")),
                gap_hit_mode=str(explain.get("gap_hit_mode") or "miss"),
                gap_source=str(explain.get("gap_source") or ""),
                gap_structure_bonus=self._d(explain.get("gap_structure_bonus")),
                gap_repair_bonus=self._d(explain.get("gap_repair_bonus")),
                repair_or_takeover_score=self._d(explain.get("repair_or_takeover_score")),
                weakness_valid_score=self._d(explain.get("weakness_valid_score")),
                transition_type=str(explain.get("transition_type") or ""),
                transition_confidence=self._d(explain.get("transition_confidence")),
                trigger_flags=list(explain.get("trigger_flags") or []),
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

        def _observe_support_priority(support_type: str) -> int:
            st = (support_type or "").strip().lower()
            if st == "gap_support":
                return 0
            if st in {"previous_low", "prev_low_support"}:
                return 1
            if st == "platform_support":
                return 2
            if st == "ma_support":
                return 3
            return 4

        def _observe_key(c: W2SCandidate) -> tuple[int, Decimal, Decimal, Decimal]:
            return (
                _observe_support_priority(c.support_type),
                -c.support_score,
                -c.weakness_valid_score,
                -c.candidate_score,
            )

        formal_candidates.sort(key=_formal_key)
        observe_candidates.sort(key=_observe_key)

        formal_top_n = 15
        observe_top_n = 10
        self._observe_candidates = observe_candidates[:observe_top_n]
        return (formal_candidates[:formal_top_n] + observe_candidates[:observe_top_n])[: self.MAX_CANDIDATES]
