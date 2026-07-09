"""Phase 4.2.1 — Phase Ontology (context-aware label mapping).

Fixes "分歧" mapping: "divergence" means different things depending on
what came before — panic→repair divergence ≠ climax→distribution divergence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ═══ Phase Context ═══

@dataclass
class PhaseContext:
    """Market context at the moment of phase classification."""
    trade_date: str = ""

    # Previous state
    prev_phase: str = ""                     # yesterday's phase label
    prev_risk: str = ""                      # yesterday's risk level

    # Today's metrics
    limit_up_count: int = 0
    limit_up_delta: int = 0                  # today - yesterday
    max_board_height: int = 0
    emotion_momentum: float = 0.0

    # Death / damage
    high_position_death_score: float = 0.0   # 0-1
    death_propagation_index: float = 0.0     # 0-100

    # Risk
    risk_level: str = ""                     # raw computed risk
    days_since_panic: int = 99               # days since last PANIC/FREEZE

    # Relay
    promotion_1_to_2: float = 0.0
    promotion_2_to_3: float = 0.0
    relay_score: float = 1.0                 # 0-1 composite relay health

    # Index confirmation
    has_index_confirmation: bool = False     # deep-V, 十字星, volume surge etc.
    up_ratio: float = 0.0
    active_capital_delta: float = 0.0        # vs yesterday

    extra: dict[str, Any] = field(default_factory=dict)


# ═══ Phase normalization ═══

def normalize_phase_label(raw_label: str, context: PhaseContext | None = None) -> str:
    """Normalize a raw AI phase label to M8 10-phase ontology.

    Context-aware: the same raw label ("分歧") maps differently
    depending on what the market was doing yesterday.
    """
    label = (raw_label or "").strip()

    # Direct matches (case-insensitive, underscore-tolerant)
    direct = _direct_match(label)
    if direct:
        return direct

    # ── "分歧" / DIVERGENCE — context-aware mapping ──
    if label in ("分歧", "DIVERGENCE"):
        return _resolve_divergence(label, context)

    # ── Fallback: unknown labels pass through ──
    return label

def _direct_match(label: str) -> str | None:
    """Exact or near-exact match to M8 ontology."""
    upper = label.upper().replace(" ", "_").replace("/", "_")
    known = {
        "PANIC", "FREEZE", "ICE_POINT", "REPAIR_WATCH", "WEAK_REPAIR",
        "REBOUND", "ACCELERATION", "CLIMAX", "FIRST_DIVERGENCE",
        "SECOND_DIVERGENCE", "DISTRIBUTION", "FADE", "SECOND_WAVE",
        "REPAIR", "退潮/冰点", "情绪退潮", "退潮",
    }
    # Map Chinese to English
    zh_map = {
        "退潮": "FADE",
        "退潮/冰点": "PANIC",
        "情绪退潮": "PANIC",
        "修复": "REPAIR_WATCH",
        "反弹": "REBOUND",
        "修复/反弹": "REBOUND",
        "加速": "ACCELERATION",
        "高潮": "CLIMAX",
        "强势": "ACCELERATION",
        "情绪正常": "ACCELERATION",
        "分歧/退潮": "FIRST_DIVERGENCE",
        # "分歧" is NOT mapped here — it goes through context-aware _resolve_divergence
        "混沌": "CHAOS",
        "启动": "REBOUND",
    }
    if label in zh_map:
        return zh_map[label]
    if upper in known or label in known:
        return label
    return None

def _resolve_divergence(label: str, context: PhaseContext | None) -> str:
    """Context-aware resolution of '分歧'."""
    if context is None:
        return "FIRST_DIVERGENCE"  # safe default

    # Rule 1: PANIC/FREEZE → limit-ups rising → likely REPAIR_WATCH
    if (context.prev_phase in ("PANIC", "FREEZE", "ICE_POINT")
            and context.limit_up_delta > 0):
        return "REPAIR_WATCH"

    # Rule 2: High death score → distribution (profit-taking)
    if context.high_position_death_score > 0.6:
        return "DISTRIBUTION"

    # Rule 3: HIGH/CRITICAL risk with death propagation → first divergence
    if (context.risk_level in ("HIGH", "CRITICAL")
            and context.death_propagation_index > 40):
        return "FIRST_DIVERGENCE"

    # Rule 4: High board still intact, emotion recovering → weak repair
    if context.max_board_height >= 5 and context.emotion_momentum > -3:
        return "WEAK_REPAIR"

    return "FIRST_DIVERGENCE"


# ═══ Risk confirmation gate ═══

def adjust_risk_by_confirmation(
    phase: str,
    raw_risk: str,
    context: PhaseContext | None = None,
) -> str:
    """Adjust raw risk level using confirmation-gate logic.

    Key rule: REBOUND day 1-2 should NOT be LOW risk.
    The most common A-short trap: mistaking a dead cat bounce for a reversal.
    """
    if context is None:
        return raw_risk

    risk_order = {"LOW": 0, "MEDIUM": 1, "MEDIUM_HIGH": 2, "HIGH": 3, "CRITICAL": 4}

    if phase == "REBOUND" and raw_risk == "LOW":
        gates = [
            (context.days_since_panic <= 2, "REBOUND within 2 days of PANIC → at least MEDIUM"),
            (context.relay_score < 0.75, "relay ecology not yet healthy → at least MEDIUM"),
            (context.high_position_death_score > 0.3, "high-position death still elevated → at least MEDIUM"),
            (not context.has_index_confirmation, "no index confirmation pattern → at least MEDIUM"),
        ]
        for triggered, reason in gates:
            if triggered:
                return "MEDIUM"

        # All gates passed: cap at MEDIUM_HIGH (never LOW on first REBOUND day)
        if context.days_since_panic <= 3:
            return "MEDIUM"

    # REBOUND + MEDIUM: allow if relay healthy + index confirmed + panic distant
    if phase == "REBOUND" and raw_risk == "MEDIUM" and context.days_since_panic > 5:
        if (context.relay_score >= 0.75
                and context.has_index_confirmation
                and context.high_position_death_score < 0.2):
            return "LOW"  # genuine reversal → OK to lower risk

    return raw_risk
