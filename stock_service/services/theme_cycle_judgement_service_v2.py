from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ThemeCycleJudgementV2:
    cycle_state_rule: str
    mainline_alive_rule: bool
    fade_watch: bool
    fade_confirmed: bool
    final_cycle_state: str
    final_mainline_alive: bool
    mainline_strength_score: float
    fade_watch_score: float
    fade_confirmed_score: float
    divergence_score: float
    repair_score: float
    rule_reasons: List[str]
    thresholds: Dict[str, float]
    score_flags: Dict[str, bool]
    evidence_refs: Dict[str, List[Dict[str, Any]]]
    decision_path: List[str]


class ThemeCycleJudgementServiceV2:
    """V2周期判定服务：从证据输入生成统一的状态机输出。"""

    RULE_VERSION = "theme_cycle_judgement.v2"
    THRESHOLDS = {
        "mainline_alive_min": 60.0,
        "mainline_alive_leader_min": 40.0,
        "mainline_alive_event_continuity_min": 40.0,
        "fade_watch_min": 50.0,
        "fade_confirmed_min": 60.0,
        "acceleration_min": 75.0,
        "repair_min": 65.0,
        "divergence_min": 60.0,
        "fermentation_min": 60.0,
    }

    def judge(self, evidence: Dict[str, Any], enable_llm_review: bool = True) -> ThemeCycleJudgementV2:
        mainline_strength_score = self._calc_mainline_strength_score(evidence)
        fade_watch_score = self._calc_fade_watch_score(evidence)
        fade_confirmed_score = self._calc_fade_confirmed_score(evidence)
        divergence_score = self._calc_divergence_score(evidence)
        repair_score = self._calc_repair_score(evidence)
        fade_confirmed_evidence_count = self._count_fade_confirmed_evidence(evidence)
        leader_alive_score = float(evidence.get("leader_alive_score") or 0.0)
        strong_event_count_7d = int(evidence.get("strong_event_count_7d") or 0)
        event_continuity_score = float(evidence.get("event_continuity_score") or 0.0)
        previous_cycle_state = str(evidence.get("previous_cycle_state") or "").lower()
        repair_transition_allowed = self._repair_transition_allowed(previous_cycle_state)

        fade_confirmed = (
            fade_confirmed_score >= self.THRESHOLDS["fade_confirmed_min"]
            and fade_confirmed_evidence_count >= 3
        )
        fade_watch = not fade_confirmed and fade_watch_score >= self.THRESHOLDS["fade_watch_min"]
        mainline_alive_rule = (
            mainline_strength_score >= self.THRESHOLDS["mainline_alive_min"]
            and leader_alive_score >= self.THRESHOLDS["mainline_alive_leader_min"]
            and (
                strong_event_count_7d > 0
                or event_continuity_score >= self.THRESHOLDS["mainline_alive_event_continuity_min"]
            )
            and (not fade_confirmed)
        )

        cycle_state_rule = self._derive_cycle_state(
            mainline_strength_score=mainline_strength_score,
            divergence_score=divergence_score,
            repair_score=repair_score,
            fade_watch=fade_watch,
            fade_confirmed=fade_confirmed,
            repair_transition_allowed=repair_transition_allowed,
            mainline_alive_rule=mainline_alive_rule,
        )

        final_cycle_state = cycle_state_rule
        final_mainline_alive = mainline_alive_rule
        evidence_refs = {
            "event": list(evidence.get("event_evidence_refs") or []),
            "leader": list(evidence.get("leader_evidence_refs") or []),
            "board": list(evidence.get("board_structure_refs") or []),
            "kline": list(evidence.get("theme_kline_refs") or []),
        }
        score_flags = {
            "mainline_alive_hit": mainline_strength_score >= self.THRESHOLDS["mainline_alive_min"],
            "mainline_leader_hit": leader_alive_score >= self.THRESHOLDS["mainline_alive_leader_min"],
            "mainline_event_hit": (
                strong_event_count_7d > 0
                or event_continuity_score >= self.THRESHOLDS["mainline_alive_event_continuity_min"]
            ),
            "fade_watch_hit": fade_watch_score >= self.THRESHOLDS["fade_watch_min"],
            "fade_confirmed_hit": fade_confirmed_score >= self.THRESHOLDS["fade_confirmed_min"],
            "fade_confirmed_evidence_count_hit": fade_confirmed_evidence_count >= 3,
            "repair_hit": repair_score >= self.THRESHOLDS["repair_min"],
            "repair_transition_allowed": repair_transition_allowed,
            "divergence_hit": divergence_score >= self.THRESHOLDS["divergence_min"],
        }
        decision_path = self._build_decision_path(
            fade_confirmed=fade_confirmed,
            fade_watch=fade_watch,
            mainline_strength_score=mainline_strength_score,
            repair_score=repair_score,
            divergence_score=divergence_score,
            repair_transition_allowed=repair_transition_allowed,
            mainline_alive_rule=mainline_alive_rule,
            fade_confirmed_evidence_count=fade_confirmed_evidence_count,
        )
        rule_reasons = self._build_reasons(
            mainline_strength_score=mainline_strength_score,
            leader_alive_score=leader_alive_score,
            fade_watch_score=fade_watch_score,
            fade_confirmed_score=fade_confirmed_score,
            fade_confirmed_evidence_count=fade_confirmed_evidence_count,
            divergence_score=divergence_score,
            repair_score=repair_score,
            previous_cycle_state=previous_cycle_state,
            repair_transition_allowed=repair_transition_allowed,
            final_cycle_state=final_cycle_state,
        )

        mainline_alive_llm = evidence.get("mainline_alive_llm")
        if (
            enable_llm_review
            and mainline_alive_llm is not None
            and cycle_state_rule in {"fade_watch", "divergence", "repair"}
        ):
            final_mainline_alive = bool(mainline_alive_llm)
            rule_reasons.append("mainline_alive_overridden_by_llm")

        if enable_llm_review:
            llm_trigger_flags = self._llm_review_trigger_flags(
                fade_watch=fade_watch,
                fade_confirmed=fade_confirmed,
                leader_alive_score=leader_alive_score,
                support_score=float(evidence.get("theme_support_score") or 0.0),
            )
            if llm_trigger_flags:
                rule_reasons.append(f"llm_review_recommended:{','.join(llm_trigger_flags)}")

        return ThemeCycleJudgementV2(
            cycle_state_rule=cycle_state_rule,
            mainline_alive_rule=mainline_alive_rule,
            fade_watch=fade_watch,
            fade_confirmed=fade_confirmed,
            final_cycle_state=final_cycle_state,
            final_mainline_alive=final_mainline_alive,
            mainline_strength_score=round(mainline_strength_score, 3),
            fade_watch_score=round(fade_watch_score, 3),
            fade_confirmed_score=round(fade_confirmed_score, 3),
            divergence_score=round(divergence_score, 3),
            repair_score=round(repair_score, 3),
            rule_reasons=rule_reasons,
            thresholds=dict(self.THRESHOLDS),
            score_flags=score_flags,
            evidence_refs=evidence_refs,
            decision_path=decision_path,
        )

    def _calc_mainline_strength_score(self, e: Dict[str, Any]) -> float:
        event = float(e.get("event_strength_score") or 0.0)
        continuity = float(e.get("event_continuity_score") or 0.0)
        leader = float(e.get("leader_alive_score") or 0.0)
        relay = float(e.get("relay_strength_score") or 0.0)
        board = float(e.get("front_row_strength_score") or 0.0)
        support = float(e.get("theme_support_score") or 0.0)
        return max(0.0, min(100.0, event * 0.22 + continuity * 0.12 + leader * 0.26 + relay * 0.16 + board * 0.14 + support * 0.10))

    def _calc_fade_watch_score(self, e: Dict[str, Any]) -> float:
        leader_break = 100.0 if bool(e.get("leader_breakdown_flag")) else 0.0
        red_ratio = float(e.get("red_ratio") or 0.0)
        big_drop = float(e.get("big_drop_ratio") or 0.0)
        limit_down = float(e.get("limit_down_count") or 0.0)
        return max(0.0, min(100.0, leader_break * 0.35 + (1.0 - red_ratio) * 45.0 + big_drop * 35.0 + min(limit_down * 10.0, 20.0)))

    def _calc_fade_confirmed_score(self, e: Dict[str, Any]) -> float:
        leader_break = 100.0 if bool(e.get("leader_breakdown_flag")) else 0.0
        limit_down = float(e.get("limit_down_count") or 0.0)
        red_ratio = float(e.get("red_ratio") or 0.0)
        relay = float(e.get("relay_strength_score") or 0.0)
        return max(0.0, min(100.0, leader_break * 0.45 + min(limit_down * 14.0, 35.0) + (1.0 - red_ratio) * 28.0 + max(0.0, 40.0 - relay) * 0.45))

    def _calc_divergence_score(self, e: Dict[str, Any]) -> float:
        leader = float(e.get("leader_alive_score") or 0.0)
        red_ratio = float(e.get("red_ratio") or 0.0)
        relay = float(e.get("relay_strength_score") or 0.0)
        front_row_survival = float(e.get("front_row_survival_ratio") or 0.0)
        support = float(e.get("theme_support_score") or 0.0)
        return max(
            0.0,
            min(
                100.0,
                leader * 0.30
                + relay * 0.25
                + front_row_survival * 20.0
                + support * 0.20
                + (1.0 - red_ratio) * 15.0,
            ),
        )

    def _calc_repair_score(self, e: Dict[str, Any]) -> float:
        continuity = float(e.get("event_continuity_score") or 0.0)
        relay = float(e.get("relay_strength_score") or 0.0)
        support = float(e.get("theme_support_score") or 0.0)
        red_ratio = float(e.get("red_ratio") or 0.0)
        leader = float(e.get("leader_alive_score") or 0.0)
        return max(
            0.0,
            min(
                100.0,
                continuity * 0.22
                + relay * 0.24
                + support * 0.20
                + red_ratio * 18.0
                + leader * 0.16,
            ),
        )

    def _repair_transition_allowed(self, previous_cycle_state: str) -> bool:
        if not previous_cycle_state:
            return False
        return previous_cycle_state in {"divergence", "fade_watch"}

    def _derive_cycle_state(
        self,
        *,
        mainline_strength_score: float,
        divergence_score: float,
        repair_score: float,
        fade_watch: bool,
        fade_confirmed: bool,
        repair_transition_allowed: bool,
        mainline_alive_rule: bool,
    ) -> str:
        if fade_confirmed:
            return "fade_confirmed"
        if repair_score >= self.THRESHOLDS["repair_min"] and repair_transition_allowed:
            return "repair"
        if divergence_score >= self.THRESHOLDS["divergence_min"]:
            return "divergence"
        if fade_watch:
            return "fade_watch"
        if mainline_strength_score >= self.THRESHOLDS["acceleration_min"]:
            return "acceleration"
        if mainline_strength_score >= self.THRESHOLDS["fermentation_min"]:
            return "fermentation"
        return "start"

    def _build_reasons(
        self,
        *,
        mainline_strength_score: float,
        leader_alive_score: float,
        fade_watch_score: float,
        fade_confirmed_score: float,
        fade_confirmed_evidence_count: int,
        divergence_score: float,
        repair_score: float,
        previous_cycle_state: str,
        repair_transition_allowed: bool,
        final_cycle_state: str,
    ) -> List[str]:
        return [
            f"mainline_strength_score={mainline_strength_score:.2f}",
            f"leader_alive_score={leader_alive_score:.2f}",
            f"fade_watch_score={fade_watch_score:.2f}",
            f"fade_confirmed_score={fade_confirmed_score:.2f}",
            f"fade_confirmed_evidence_count={fade_confirmed_evidence_count}",
            f"divergence_score={divergence_score:.2f}",
            f"repair_score={repair_score:.2f}",
            f"previous_cycle_state={previous_cycle_state or 'none'}",
            f"repair_transition_allowed={repair_transition_allowed}",
            f"final_cycle_state={final_cycle_state}",
        ]

    def _build_decision_path(
        self,
        *,
        fade_confirmed: bool,
        fade_watch: bool,
        mainline_strength_score: float,
        repair_score: float,
        divergence_score: float,
        repair_transition_allowed: bool,
        mainline_alive_rule: bool,
        fade_confirmed_evidence_count: int,
    ) -> List[str]:
        path: List[str] = []
        if fade_confirmed:
            path.append("fade_confirmed -> final=fade_confirmed")
            return path
        if repair_score >= self.THRESHOLDS["repair_min"] and repair_transition_allowed:
            path.append("repair_score>=repair_min -> final=repair")
            return path
        if repair_score >= self.THRESHOLDS["repair_min"] and not repair_transition_allowed:
            path.append("repair_score>=repair_min but previous_state_not_allowed -> keep evaluating")
        if divergence_score >= self.THRESHOLDS["divergence_min"]:
            path.append("divergence_score>=divergence_min -> final=divergence")
            return path
        if fade_watch:
            path.append("fade_watch -> final=fade_watch")
            return path
        if mainline_strength_score >= self.THRESHOLDS["acceleration_min"]:
            path.append("mainline_strength>=acceleration_min -> final=acceleration")
            return path
        if mainline_strength_score >= self.THRESHOLDS["fermentation_min"]:
            path.append("mainline_strength>=fermentation_min -> final=fermentation")
            return path
        if fade_confirmed_evidence_count > 0:
            path.append(f"fade_confirmed_evidence_count={fade_confirmed_evidence_count}(<3) -> not_confirmed")
        path.append("fallback -> final=start")
        return path

    def _count_fade_confirmed_evidence(self, e: Dict[str, Any]) -> int:
        hits = 0
        if bool(e.get("leader_breakdown_flag")):
            hits += 1
        if float(e.get("limit_down_count") or 0.0) >= 1.0:
            hits += 1
        if float(e.get("red_ratio") or 0.0) <= 0.45:
            hits += 1
        if float(e.get("big_drop_ratio") or 0.0) >= 0.30:
            hits += 1
        if float(e.get("relay_strength_score") or 0.0) <= 35.0:
            hits += 1
        if float(e.get("theme_support_score") or 0.0) <= 35.0:
            hits += 1
        return hits

    def _llm_review_trigger_flags(
        self,
        *,
        fade_watch: bool,
        fade_confirmed: bool,
        leader_alive_score: float,
        support_score: float,
    ) -> List[str]:
        flags: List[str] = []
        if fade_watch:
            flags.append("fade_watch_state")
        if fade_confirmed and leader_alive_score >= 55.0 and support_score >= 70.0:
            flags.append("fade_confirmed_but_core_supportive")
        return flags
