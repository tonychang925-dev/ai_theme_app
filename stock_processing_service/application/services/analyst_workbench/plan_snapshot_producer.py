"""PlanSnapshotProducer — derive plan_state from emotion + market inputs.

This producer applies deterministic rules to the emotion_node (a canonical
fact from the emotion pipeline) to produce structured plan_state. It does
NOT read the database, call LLMs, or infer from unrelated fields.

The output is consumed by DraftContextBuilder and persisted in draft_context.
ContextFactory reads plan_state from derived context to build PlanContext.
"""

from __future__ import annotations

from typing import Any

# ── Rule table: emotion_node → scenario + allowed + forbidden ──

_PLAN_RULES: dict[str, dict[str, Any]] = {
    "ICE_POINT": {
        "scenario": "冰点修复",
        "allowed": ["观察", "左侧轻仓试错"],
        "forbidden": ["重仓", "追高", "打板"],
    },
    "DIVERGENCE": {
        "scenario": "退潮观望",
        "allowed": ["观察", "持有现金"],
        "forbidden": ["抄底", "追高", "打板"],
    },
    "FADE": {
        "scenario": "退潮观望",
        "allowed": ["观察", "持有现金"],
        "forbidden": ["抄底", "追高", "打板"],
    },
    "REBOUND": {
        "scenario": "修复持有",
        "allowed": ["持有", "观察持续性"],
        "forbidden": ["追高", "重仓"],
    },
    "REPAIR": {
        "scenario": "修复持有",
        "allowed": ["持有", "观察持续性"],
        "forbidden": ["追高", "重仓"],
    },
    "FERMENTATION": {
        "scenario": "主线进攻",
        "allowed": ["持仓", "关注龙头晋级"],
        "forbidden": ["追高位"],
    },
    "ACCELERATION": {
        "scenario": "主线进攻",
        "allowed": ["持仓", "关注龙头加速"],
        "forbidden": ["追高位"],
    },
    "CLIMAX": {
        "scenario": "高潮警惕",
        "allowed": ["持有", "观察分歧信号"],
        "forbidden": ["追龙头", "新开高位仓位"],
    },
    "CHAOS": {
        "scenario": "混沌观望",
        "allowed": ["观察", "轻仓"],
        "forbidden": ["重仓", "追高"],
    },
}


class PlanSnapshotProducer:
    """Produce plan_state from emotion_state + theme data.

    This is a Snapshot Producer: it reads canonical inputs (emotion_node,
    theme cycle rows) and outputs structured plan_state. No DB, no LLM,
    no inference from unrelated fields.
    """

    def produce(
        self,
        emotion_state: dict[str, Any],
        themes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Derive plan_state from emotion node + theme state.

        Args:
            emotion_state: Canonical emotion state (must have emotion_node).
            themes: Theme cycle rows with mainline_strength_score.

        Returns:
            plan_state dict with scenario, allowed_actions, forbidden_actions,
            watch_themes, watch_stocks, confirmation_signals, invalidation_signals.
        """
        node = str(emotion_state.get("emotion_node") or "")
        rules = _PLAN_RULES.get(node, _PLAN_RULES["CHAOS"])

        # Watch themes: top 5 by mainline_strength_score
        ranked = sorted(
            [t for t in themes if isinstance(t, dict)],
            key=lambda t: float(t.get("mainline_strength_score") or 0),
            reverse=True,
        )
        watch_themes: list[dict[str, Any]] = []
        for t in ranked[:5]:
            key = str(t.get("subject_key") or "")
            name = str(t.get("theme_name") or key)
            if key:
                watch_themes.append({
                    "subject_key": key,
                    "theme_name": name,
                    "stage": str(t.get("stage") or t.get("final_cycle_state") or ""),
                    "strength_score": float(t.get("mainline_strength_score") or 0),
                })

        return {
            "scenario": rules["scenario"],
            "emotion_node": node,
            "allowed_actions": list(rules["allowed"]),
            "forbidden_actions": list(rules["forbidden"]),
            "watch_themes": watch_themes,
            "watch_stocks": [],
            "confirmation_signals": [],
            "invalidation_signals": [],
        }
