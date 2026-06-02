"""MainlineDiscoveryEngine — Phase 1 PR-5.

Orchestrates 4 evidence blocks to produce machine candidate states.

Evidence blocks (by subject_key):
  logic_evidence       → rule_logic_score + continuity + impact + novelty
  market_acceptance    → market_acceptance_score + veto flags
  major_event_classifier → major_event_score + is_fast_line_trigger
  narrative_judge      → llm_narrative_score + narrative_level

Output: MainlineDiscoveryDecision per subject with machine_state.
  machine_fast_candidate / machine_slow_candidate / logic_only /
  market_noise / rotation_hotspot / rejected

Critical constraint: NEVER outputs final_mainline_state = confirmed_mainline.
All candidates go through human review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import MainlineDiscoveryDecision


@dataclass
class MainlineDiscoveryEngine:
    """Combine evidence blocks into machine candidate states.

    Does NOT confirm mainlines. Generates machine candidates only.
    All fast/slow candidates require human review.
    """

    # ── thresholds ──
    FAST_LINE_MAJOR_EVENT_MIN: float = 85.0
    FAST_LINE_MARKET_MIN: float = 55.0
    SLOW_LINE_HYBRID_MIN: float = 70.0
    SLOW_LINE_MARKET_MIN: float = 65.0
    SLOW_LINE_NARRATIVE_MIN: float = 70.0
    LOGIC_ONLY_HYBRID_MIN: float = 70.0
    MARKET_NOISE_MARKET_MIN: float = 65.0
    ROTATION_LOWER: float = 45.0
    ROTATION_UPPER: float = 70.0

    def evaluate(
        self,
        *,
        subject_key: str,
        theme_name: str = "",
        logic_evidence: dict[str, Any] | None = None,
        market_acceptance: dict[str, Any] | None = None,
        major_event_classification: dict[str, Any] | None = None,
        narrative_judge: dict[str, Any] | None = None,
    ) -> MainlineDiscoveryDecision:

        le = logic_evidence or {}
        ma = market_acceptance or {}
        mc = major_event_classification or {}
        nj = narrative_judge or {}

        # ── extract scores ──
        rule_logic = _float(le.get("logic_score"))
        llm_narrative = _float(nj.get("narrative_score"))
        market_score = _float(ma.get("market_acceptance_score"))
        major_score = _float(mc.get("major_event_score"))
        is_fast_trigger = bool(mc.get("is_fast_line_trigger", False))

        # ── sub-scores for hybrid ──
        continuity = _float(le.get("event_continuity_score")) or 0
        impact = _float(le.get("event_impact_score")) or 0
        novelty = _float(le.get("novelty_score")) or 0

        # ── hybrid logic score ──
        hybrid, method = self._compute_hybrid(rule_logic, llm_narrative, continuity, impact, novelty, nj)

        # ── vetoes ──
        blocking = list(ma.get("blocking_veto_flags", []) or [])
        confirmation = list(ma.get("confirmation_veto_flags", []) or [])
        has_blocking = bool(blocking)
        leader_alive = bool(ma.get("leader_alive", False))
        leader_not_alive = "leader_not_alive" in confirmation

        # ── scoring ──
        fast_score = None
        slow_score = None
        if is_fast_trigger and major_score and market_score:
            fast_score = round(major_score * 0.50 + market_score * 0.30 + (hybrid or 0) * 0.20, 1)
        if market_score and hybrid:
            slow_score = round(hybrid * 0.45 + market_score * 0.35 + (continuity or 0) * 0.20, 1)

        # ── decision state machine ──
        decision = self._decide(
            is_fast_trigger, major_score, market_score, hybrid, llm_narrative,
            has_blocking, leader_not_alive, leader_alive, fast_score, slow_score,
        )

        return MainlineDiscoveryDecision(
            subject_key=subject_key,
            theme_name=theme_name,
            machine_state=decision["machine_state"],
            final_mainline_state=decision["final_mainline_state"],
            mainline_type=decision.get("mainline_type", "unknown"),
            confirmation_path=decision.get("confirmation_path", "unknown"),
            trigger_mode=str(mc.get("trigger_type") or "unknown"),
            human_review_required=decision["human_review_required"],
            human_review_status="pending" if decision["human_review_required"] else "none",
            review_reason=decision.get("review_reason", ""),
            suggested_human_decision=decision.get("suggested_human_decision", "watch"),
            rule_logic_score=rule_logic,
            llm_narrative_score=llm_narrative,
            hybrid_logic_score=hybrid,
            market_acceptance_score=market_score,
            major_event_score=major_score,
            fast_line_score=fast_score,
            slow_line_score=slow_score,
            blocking_veto_flags=blocking,
            confirmation_veto_flags=confirmation,
            logic_score_method=method,
            diagnostics={
                "decision_path": decision.get("decision_path", ""),
                "blocking_veto_count": len(blocking),
                "confirmation_veto_count": len(confirmation),
                "leader_alive": leader_alive,
                "is_fast_line_trigger": is_fast_trigger,
                "hybrid_logic_score": hybrid,
                "llm_narrative_score": llm_narrative,
                "market_acceptance_score": market_score,
                "major_event_score": major_score,
            },
        )

    def _compute_hybrid(
        self,
        rule: float | None,
        llm: float | None,
        continuity: float,
        impact: float,
        novelty: float,
        nj: dict[str, Any],
    ) -> tuple[float | None, str]:
        """Compute hybrid logic score. Fall back to rule if LLM unavailable."""
        llm_unavailable = nj.get("narrative_level") in {"unavailable", None}
        llm_empty_ids = not nj.get("supporting_event_ids")

        if llm is not None and not llm_unavailable:
            score = llm * 0.55 + continuity * 0.20 + impact * 0.15 + novelty * 0.10
            # Cap only when LLM is used but supporting IDs are empty
            if llm_empty_ids:
                score = min(score, 49.0)
            method = "hybrid_v1"
        elif rule is not None:
            score = rule
            method = "rule_fallback" if llm_unavailable else "rule_fallback_llm_unavailable"
        else:
            return None, "no_data"

        return round(score, 1), method

    def _decide(
        self,
        is_fast: bool,
        major_score: float | None,
        market: float | None,
        hybrid: float | None,
        llm_narrative: float | None,
        has_blocking: bool,
        leader_not_alive: bool,
        leader_alive: bool,
        fast_score: float | None,
        slow_score: float | None,
    ) -> dict[str, Any]:
        # ── blocking veto → rejected ──
        if has_blocking:
            return {
                "machine_state": "rejected",
                "final_mainline_state": "rejected",
                "human_review_required": False,
                "review_reason": "blocking_veto",
                "suggested_human_decision": "reject",
                "decision_path": "blocking_veto_active",
            }

        market_val = market or 0
        hybrid_val = hybrid or 0
        major_val = major_score or 0
        llm_val = llm_narrative or 0

        # ── fast line candidate ──
        if is_fast and major_val >= self.FAST_LINE_MAJOR_EVENT_MIN and market_val >= self.FAST_LINE_MARKET_MIN:
            return {
                "machine_state": "machine_fast_candidate",
                "final_mainline_state": "pending_review",
                "mainline_type": "fast_line",
                "confirmation_path": "fast_event_driven",
                "human_review_required": True,
                "review_reason": "major_event_trigger",
                "suggested_human_decision": "confirm_mainline",
                "decision_path": f"fast_line: major_event>={self.FAST_LINE_MAJOR_EVENT_MIN} and market>={self.FAST_LINE_MARKET_MIN}",
            }

        # ── slow line candidate ──
        if (hybrid_val >= self.SLOW_LINE_HYBRID_MIN
                and market_val >= self.SLOW_LINE_MARKET_MIN
                and llm_val >= self.SLOW_LINE_NARRATIVE_MIN
                and not leader_not_alive):
            return {
                "machine_state": "machine_slow_candidate",
                "final_mainline_state": "pending_review",
                "mainline_type": "slow_line",
                "confirmation_path": "slow_accumulation",
                "human_review_required": True,
                "review_reason": "slow_line_evidence_ready",
                "suggested_human_decision": "confirm_mainline",
                "decision_path": f"slow_line: hybrid>={self.SLOW_LINE_HYBRID_MIN} and market>={self.SLOW_LINE_MARKET_MIN} and narrative>={self.SLOW_LINE_NARRATIVE_MIN}",
            }

        # ── logic_only ──
        if hybrid_val >= self.LOGIC_ONLY_HYBRID_MIN and market_val < self.FAST_LINE_MARKET_MIN:
            review = hybrid_val >= 80 and market_val >= 45
            return {
                "machine_state": "logic_only",
                "final_mainline_state": "logic_only",
                "human_review_required": review,
                "review_reason": "logic_strong_but_market_not_confirmed",
                "suggested_human_decision": "watch" if not review else "confirm_mainline",
                "decision_path": f"logic_only: hybrid>={self.LOGIC_ONLY_HYBRID_MIN} and market<{self.FAST_LINE_MARKET_MIN}",
            }

        # ── market_noise ──
        if market_val >= self.MARKET_NOISE_MARKET_MIN and hybrid_val < 55:
            review = market_val >= 75
            return {
                "machine_state": "market_noise",
                "final_mainline_state": "market_noise",
                "human_review_required": review,
                "review_reason": "market_hot_but_logic_unclear",
                "suggested_human_decision": "reject_or_watch",
                "decision_path": f"market_noise: market>={self.MARKET_NOISE_MARKET_MIN} and hybrid<55",
            }

        # ── rotation_hotspot ──
        if self.ROTATION_LOWER <= hybrid_val <= self.ROTATION_UPPER and self.ROTATION_LOWER <= market_val <= self.ROTATION_UPPER:
            return {
                "machine_state": "rotation_hotspot",
                "final_mainline_state": "rotation_hotspot",
                "human_review_required": False,
                "review_reason": "moderate_logic_and_market",
                "suggested_human_decision": "watch",
                "decision_path": f"rotation: hybrid {hybrid_val:.0f} market {market_val:.0f} both moderate",
            }

        # ── rejected ──
        return {
            "machine_state": "rejected",
            "final_mainline_state": "rejected",
            "human_review_required": False,
            "review_reason": "insufficient_evidence",
            "suggested_human_decision": "reject",
            "decision_path": f"rejected: hybrid={hybrid_val:.0f} market={market_val:.0f}",
        }

    def evaluate_all(
        self,
        *,
        candidate_subjects: list[dict[str, Any]],
        logic_evidence_by_subject: dict[str, dict[str, Any]] | None = None,
        market_acceptance_by_subject: dict[str, dict[str, Any]] | None = None,
        major_event_by_subject: dict[str, dict[str, Any]] | None = None,
        narrative_by_subject: dict[str, dict[str, Any]] | None = None,
        active_mainline_universe: Any | None = None,
    ) -> list[MainlineDiscoveryDecision]:
        logic_map = logic_evidence_by_subject or {}
        market_map = market_acceptance_by_subject or {}
        major_map = major_event_by_subject or {}
        narrative_map = narrative_by_subject or {}

        results: list[MainlineDiscoveryDecision] = []
        existing_mainline_updates: list[dict[str, Any]] = []

        # Import here to avoid circular dependency
        from stock_processing_service.application.services.active_mainline_universe_builder import (
            ActiveMainlineUniverseBuilder,
        )

        for cand in candidate_subjects:
            sk = str(cand.get("subject_key", ""))
            if not sk:
                continue
            tn = str(cand.get("theme_name", sk))

            # ── PR-13A: check dedup against active mainlines ──
            dup_info = None
            if active_mainline_universe is not None:
                dup_info = ActiveMainlineUniverseBuilder.is_duplicate_of_active(
                    sk, active_mainline_universe
                )

            if dup_info:
                # Not a new mainline candidate — record as existing mainline event
                le = logic_map.get(sk, {})
                ev_chain = le.get("event_chain", []) if isinstance(le, dict) else []
                existing_mainline_updates.append({
                    "subject_key": sk,
                    "theme_name": tn,
                    "machine_state": dup_info["machine_state"],
                    "target_mainline_id": dup_info["target_mainline_id"],
                    "target_mainline_name": dup_info["target_mainline_name"],
                    "match_type": dup_info["match_type"],
                    "event_count": len(ev_chain) if isinstance(ev_chain, list) else 0,
                    "review_required": False,
                })
                # Create a decision with existing_mainline state (for diagnostics / daily_state)
                decision = MainlineDiscoveryDecision(
                    subject_key=sk,
                    theme_name=tn,
                    machine_state=dup_info["machine_state"],
                    final_mainline_state="existing_mainline_event",
                    human_review_required=False,
                    human_review_status="none",
                    review_reason=dup_info["match_type"] + "_dedup",
                    suggested_human_decision="none",
                    diagnostics={
                        "dedup_match_type": dup_info["match_type"],
                        "target_mainline_id": dup_info["target_mainline_id"],
                        "target_mainline_name": dup_info["target_mainline_name"],
                        "existing_event_count": len(ev_chain) if isinstance(ev_chain, list) else 0,
                    },
                )
                results.append(decision)
                continue

            le = logic_map.get(sk, {})
            ma = market_map.get(sk, {})
            if hasattr(ma, 'to_dict'):
                ma = ma.to_dict()
            mc = major_map.get(sk, {})
            nj = narrative_map.get(sk, {})
            if hasattr(nj, 'to_dict'):
                nj = nj.to_dict()

            decision = self.evaluate(
                subject_key=sk,
                theme_name=tn,
                logic_evidence=le,
                market_acceptance=ma,
                major_event_classification=mc,
                narrative_judge=nj,
            )
            results.append(decision)

        # Sort: fast/slow candidates first, then existing mainline events, then by score
        def _sort_key(d: MainlineDiscoveryDecision) -> tuple[int, float]:
            order = {
                "machine_fast_candidate": 0,
                "machine_slow_candidate": 1,
                "existing_mainline_strengthening": 2,
                "existing_mainline_branch_event": 3,
                "logic_only": 4,
                "market_noise": 5,
                "rotation_hotspot": 6,
                "rejected": 7,
            }
            score = max(d.fast_line_score or 0, d.slow_line_score or 0, d.hybrid_logic_score or 0)
            return (order.get(d.machine_state, 99), -score)

        results.sort(key=_sort_key)
        return results


def _float(val: Any) -> float | None:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except Exception:
        return None
