"""PR-10B: MainlineLifecycleLayerBAdapter.

Reuses Layer B (theme_cycle_judgement_v2 + theme_cycle_evidence_daily)
to produce mainline lifecycle reviews. Does NOT rewrite lifecycle logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .models import MainlineLifecycleReview, MainlineLifecycleFactContext


def _float(val: Any) -> float | None:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except Exception:
        return None


_STATE_MAP: dict[str, str] = {
    "seed": "seed",
    "start": "start",
    "fermentation": "fermentation",
    "acceleration": "acceleration",
    "climax": "climax",
    "divergence": "divergence",
    "repair": "repair",
    "fade_watch": "fade_watch",
    "fade_confirmed": "fade_confirmed",
    "dead": "dead",
}


def _playability(state: str, alive: bool, fade_risk: float | None, fade_confirmed: float | None) -> dict[str, Any]:
    if not alive or state == "dead":
        return {"can_watch": False, "can_trade_if_market_safe": False,
                "preferred_setup": "none", "forbidden_setup": ["all"]}
    if state in {"fade_confirmed", "fade_watch"}:
        return {"can_watch": True, "can_trade_if_market_safe": False,
                "preferred_setup": "observe_only", "forbidden_setup": ["chase", "new_position",
                 "average_down", "high_consistency_chasing"]}
    if state in {"seed", "start"}:
        return {"can_watch": True, "can_trade_if_market_safe": True,
                "preferred_setup": "leader_confirmation_or_first_consolidation",
                "forbidden_setup": ["rear_chasing", "heavy_position"]}
    if state in {"fermentation", "acceleration"}:
        return {"can_watch": True, "can_trade_if_market_safe": True,
                "preferred_setup": "core_consolidation_or_leader_rotation",
                "forbidden_setup": ["rear_chasing", "high_consistency_chasing"]}
    if state == "climax":
        return {"can_watch": True, "can_trade_if_market_safe": True,
                "preferred_setup": "core_only",
                "forbidden_setup": ["new_position", "rear_chasing", "heavy_position"]}
    if state in {"divergence", "repair"}:
        return {"can_watch": True, "can_trade_if_market_safe": True,
                "preferred_setup": "core_weak_to_strong_or_divergence_repair",
                "forbidden_setup": ["rear_chasing", "high_consistency_chasing", "non_core_chasing"]}

    return {"can_watch": True, "can_trade_if_market_safe": True,
            "preferred_setup": "standard", "forbidden_setup": ["rear_chasing"]}


@dataclass
class MainlineLifecycleLayerBAdapter:
    """Adapter that maps Layer B judgement data to mainline lifecycle."""

    def build(
        self,
        *,
        trade_date: str,
        fact_ctx: MainlineLifecycleFactContext,
    ) -> tuple[list[MainlineLifecycleReview], dict[str, Any]]:
        reviews: list[MainlineLifecycleReview] = []
        missing_jd_count = 0
        fade_confirmed_count = 0
        trade_alive_count = 0
        total_related_states = 0

        for ml in fact_ctx.confirmed_mainlines:
            ml_id = str(ml.get("mainline_id") or "")
            ml_name = str(ml.get("mainline_name") or "")
            csk = str(ml.get("canonical_subject_key") or "")

            if not csk:
                continue

            # ── Layer B judgement for canonical subject ──
            jd = fact_ctx.cycle_judgement_by_sk.get(csk, {})
            ev = fact_ctx.cycle_evidence_by_sk.get(csk, {})

            if not jd:
                missing_jd_count += 1
                # No Layer B data — conservatively assume alive but NOT trade_alive.
                # This prevents false no_confirmed_mainline while still blocking trading
                # until cycle_judgement data catches up.
                reviews.append(MainlineLifecycleReview(
                    trade_date=trade_date, mainline_id=ml_id, mainline_name=ml_name,
                    canonical_subject_key=csk,
                    lifecycle_state="unknown", mainline_alive=True, mainline_trade_alive=False,
                    lifecycle_source="theme_cycle_judgement_v2", source_subject_key=csk,
                    playability={"can_watch": True, "can_trade_if_market_safe": False,
                                 "preferred_setup": "observe_only",
                                 "forbidden_setup": ["new_position", "chase"]},
                    diagnostics={"layer_b_reused": False, "mode": "missing_layer_b_judgement",
                                 "missing_layer_b_judgement": True,
                                 "assume_alive": True},
                ))
                continue

            # ── map Layer B fields ──
            raw_state = str(jd.get("final_cycle_state") or jd.get("state") or "unknown")
            lifecycle_state = _STATE_MAP.get(raw_state, raw_state)
            alive = bool(jd.get("final_mainline_alive", False))

            # PR-13B: trade_alive is only False for truly dead states or hard vetoes.
            # divergence/repair are alive states — trading permission is gated by MarketRegime.
            fade_risk = _float(jd.get("fade_risk_score"))
            fade_confirmed = _float(jd.get("fade_confirmed_score"))
            fade_watch = _float(jd.get("fade_watch_score"))
            strength = _float(jd.get("mainline_strength_score"))
            support_break = bool(jd.get("support_break", False))
            leader_breakdown = bool(jd.get("leader_breakdown", False))
            reason_codes = list(jd.get("fade_reason_codes") or [])

            # Hard vetoes: these override alive=True → trade_alive=False
            hard_veto = (
                lifecycle_state in {"fade_confirmed", "dead"}
                or support_break
                or leader_breakdown
                or (fade_risk is not None and fade_risk >= 80)
            )
            trade_alive = alive and not hard_veto

            # ── risk state ──
            risk = "normal"
            if not alive:
                risk = "inactive"
            elif hard_veto:
                risk = "inactive"
            elif trade_alive and (fade_confirmed or 0) >= 50:
                risk = "high_fade_risk"
            elif trade_alive and (fade_watch or 0) >= 50:
                risk = "elevated_fade_watch"
            elif not trade_alive:
                risk = "inactive"

            # ── related subjects ──
            related_json = ml.get("related_subject_keys_json")
            if isinstance(related_json, str):
                try:
                    related_json = json.loads(related_json)
                except Exception:
                    related_json = []
            related_keys = related_json if isinstance(related_json, list) else []
            related_states: list[dict[str, Any]] = []
            for rsk in related_keys:
                rjd = fact_ctx.cycle_judgement_by_sk.get(str(rsk), {})
                if rjd:
                    related_states.append({
                        "subject_key": str(rsk),
                        "final_cycle_state": str(rjd.get("final_cycle_state") or "unknown"),
                        "mainline_strength_score": _float(rjd.get("mainline_strength_score")),
                    })

            if trade_alive:
                trade_alive_count += 1
            if lifecycle_state in {"fade_confirmed", "fade_watch"}:
                fade_confirmed_count += 1
            total_related_states += len(related_states)

            reviews.append(MainlineLifecycleReview(
                trade_date=trade_date, mainline_id=ml_id, mainline_name=ml_name,
                canonical_subject_key=csk, related_subject_keys=related_keys,
                lifecycle_state=lifecycle_state, mainline_alive=alive,
                mainline_trade_alive=trade_alive, risk_state=risk,
                mainline_strength_score=strength, fade_risk_score=fade_risk,
                fade_watch_score=fade_watch, fade_confirmed_score=fade_confirmed,
                support_break=support_break, fade_reason_codes=reason_codes,
                lifecycle_source="theme_cycle_judgement_v2", source_subject_key=csk,
                related_subject_states=related_states,
                playability=_playability(lifecycle_state, alive, fade_risk, fade_confirmed),
                diagnostics={"layer_b_reused": True, "mode": "direct_canonical_subject",
                             "missing_layer_b_judgement": False, "aggregation_used": False},
            ))

        diag = {
            "confirmed_mainline_count": len(fact_ctx.confirmed_mainlines),
            "lifecycle_review_count": len(reviews),
            "missing_layer_b_judgement_count": missing_jd_count,
            "related_subject_state_count": total_related_states,
            "fade_confirmed_count": fade_confirmed_count,
            "trade_alive_count": trade_alive_count,
            "source": "theme_cycle_judgement_v2",
            "layer_b_reused": True,
        }
        return reviews, diag
