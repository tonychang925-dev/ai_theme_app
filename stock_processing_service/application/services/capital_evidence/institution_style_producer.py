"""PR4.2.33a — Institution Style Producer (Core Multi-Signal Model).

Answers: "Which themes are becoming preferred by medium-term institutional capital?"

4-signal weighted model:
  S1 Theme Fund Flow (35%): persistence + acceleration + large_flow_ratio + consistency
  S2 Industry Cycle (30%): 7-stage lifecycle bonus + transition direction
  S3 Stock Structure (25%): leader quality + core stock strength + breadth depth
  S4 Dragon Tiger (10%): seat quality weighted + institution buy intensity

DT-missing: weights redistributed, dynamic confidence penalty.
Market regime modifier: deferred to PR4.2.33b (factor=1.0 in 33a).

Forbidden: single-signal inference, net_amount>0 → institution_style,
direct UI/ReviewDocument connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import sqrt
from typing import Any

# ── Constants ──

MODEL_VERSION = "institution_style_v1"
SOURCE = "institution_style_producer"

# S1 sub-weights (flow_score)
W_PERSISTENCE = 0.30
W_ACCELERATION = 0.25
W_LARGE_RATIO = 0.20
W_CONSISTENCY = 0.25

# Signal weights (composite)
W_FLOW = 0.35
W_CYCLE = 0.30
W_STRUCTURE = 0.25
W_DRAGON_TIGER = 0.10

# S2 stage bonus (7-stage model)
STAGE_BONUS: dict[str, float] = {
    "START": 0.65,
    "INCUBATION": 0.75,
    "FERMENTATION": 0.85,
    "DIFFUSION": 0.80,
    "PEAK": 0.45,
    "DISTRIBUTION": 0.20,
    "DECAY": 0.05,
}
DEFAULT_STAGE_BONUS = 0.50

# Transition bonus
TRANSITION_UP = 0.10       # → FERMENTATION/INCUBATION
TRANSITION_UP_MILD = 0.05  # → DIFFUSION
TRANSITION_DOWN = -0.12    # → PEAK/DISTRIBUTION
TRANSITION_COLLAPSE = -0.18  # → DECAY

# S3 sub-weights
W_LEADER = 0.40
W_CORE = 0.35
W_BREADTH = 0.25

# S4 seat quality
SEAT_QUALITY: dict[str, float] = {
    "机构专用": 1.0,
    "知名游资": 0.8,
    "普通营业部": 0.3,
}
DEFAULT_SEAT_QUALITY = 0.5

# Coverage threshold
COVERAGE_THRESHOLD = 0.50

# Confidence
BASE_CONFIDENCE = 0.85
DT_MISSING_CONF_PENALTY_STRONG = 0.95   # core signals strong → only 5% penalty
DT_MISSING_CONF_PENALTY_WEAK = 0.85     # core signals weak → 15% penalty
EVIDENCE_COMPLETENESS_PER_SIGNAL = 0.05


# ── Output ──

@dataclass(frozen=True, slots=True)
class InstitutionStyleOutput:
    trade_date: date
    subject_key: str
    theme_name: str

    institution_score: float
    base_score: float
    confidence: float
    market_regime_factor: float

    flow_score: float | None
    cycle_score: float | None
    structure_score: float | None
    dragon_tiger_score: float | None

    lifecycle_stage: str
    evidence_quality: dict[str, str]
    evidence: dict[str, Any]
    top_signals: list[str]

    model_version: str = MODEL_VERSION
    source: str = SOURCE

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "subject_key": self.subject_key,
            "theme_name": self.theme_name,
            "institution_score": self.institution_score,
            "base_score": self.base_score,
            "confidence": self.confidence,
            "market_regime_factor": self.market_regime_factor,
            "flow_score": self.flow_score,
            "cycle_score": self.cycle_score,
            "structure_score": self.structure_score,
            "dragon_tiger_score": self.dragon_tiger_score,
            "lifecycle_stage": self.lifecycle_stage,
            "evidence_quality": self.evidence_quality,
            "evidence": self.evidence,
            "top_signals": list(self.top_signals),
            "model_version": self.model_version,
            "source": self.source,
        }


# ── Producer ──

class InstitutionStyleProducer:
    """Produce institution_style scores from multi-signal evidence.

    All formulas are deterministic. No randomness, no LLM, no DB inside.
    Market regime factor is 1.0 in PR4.2.33a (deferred to 33b).
    """

    def produce(
        self,
        theme_flows: list[dict[str, Any]],
        theme_cycles: list[dict[str, Any]],
        stock_structures: dict[str, list[dict[str, Any]]],
        dragon_tiger: dict[str, list[dict[str, Any]]] | None = None,
        *,
        market_regime_factor: float = 1.0,
    ) -> list[InstitutionStyleOutput]:
        """Produce institution style scores for all themes.

        Args:
            theme_flows: Rows from theme_capital_flow_daily.
            theme_cycles: Rows from theme_cycle_judgement_v2.
            stock_structures: {subject_key: [stock rows from strong_stock_watch_history]}.
            dragon_tiger: {subject_key: [seat rows]} or None if unavailable.
            market_regime_factor: 1.0 in 33a, variable in 33b.

        Returns:
            List of InstitutionStyleOutput, one per theme with sufficient data.
        """
        dt = dragon_tiger or {}

        # Index cycles by subject_key
        cycle_by_key: dict[str, dict[str, Any]] = {}
        for c in theme_cycles:
            key = str(c.get("subject_key") or "").strip()
            if key:
                cycle_by_key[key] = c

        results: list[InstitutionStyleOutput] = []
        td = _trade_date_from(theme_flows)

        for flow in theme_flows:
            key = str(flow.get("subject_key") or "").strip()
            if not key:
                continue
            name = str(flow.get("theme_name") or key)

            # S1: Fund flow score
            flow_score, flow_quality, flow_signals = _compute_flow_score(flow)

            # S2: Cycle score
            cycle_row = cycle_by_key.get(key, {})
            cycle_score, cycle_quality, cycle_signals, lifecycle_stage = _compute_cycle_score(cycle_row)

            # S3: Structure score
            stocks = stock_structures.get(key, [])
            structure_score, structure_quality, structure_signals = _compute_structure_score(stocks)

            # S4: Dragon tiger score
            seats = dt.get(key, [])
            dt_score, dt_quality, dt_signals = _compute_dragon_tiger_score(seats)

            # Determine if DT is missing
            dt_missing = dt_score is None

            # Compute base score with weight redistribution if DT missing
            if dt_missing:
                # Redistribute S4 weight: S1+4%, S2+3%, S3+3%
                w_flow_eff = W_FLOW + 0.04
                w_cycle_eff = W_CYCLE + 0.03
                w_structure_eff = W_STRUCTURE + 0.03
                w_dt_eff = 0.0
                dt_eff_score = 0.0
            else:
                w_flow_eff = W_FLOW
                w_cycle_eff = W_CYCLE
                w_structure_eff = W_STRUCTURE
                w_dt_eff = W_DRAGON_TIGER
                dt_eff_score = dt_score or 0.0

            base_score = (
                w_flow_eff * (flow_score or 0.0)
                + w_cycle_eff * (cycle_score or 0.0)
                + w_structure_eff * (structure_score or 0.0)
                + w_dt_eff * dt_eff_score
            )

            final_score = round(base_score * market_regime_factor, 2)
            base_score = round(base_score, 2)

            # Confidence
            coverage = float(flow.get("flow_coverage_ratio") or 0.0)
            coverage_factor = min(1.0, coverage / 0.70) if coverage > 0 else 0.5
            missing_count = sum(1 for s in [flow_score, cycle_score, structure_score] if s is None)
            evidence_completeness = 1.0 - (EVIDENCE_COMPLETENESS_PER_SIGNAL * missing_count)

            conf = BASE_CONFIDENCE * coverage_factor * evidence_completeness
            if dt_missing:
                if flow_quality == "HIGH" and cycle_quality == "HIGH":
                    conf *= DT_MISSING_CONF_PENALTY_STRONG
                else:
                    conf *= DT_MISSING_CONF_PENALTY_WEAK
            conf = round(min(1.0, max(0.0, conf)), 4)

            # Evidence quality
            evidence_quality = {
                "flow": flow_quality,
                "cycle": cycle_quality,
                "structure": structure_quality,
                "dragon_tiger": dt_quality,
            }

            # Aggregate signals for explanation
            top_signals = flow_signals + cycle_signals + structure_signals + dt_signals

            evidence = {
                "flow_coverage_ratio": coverage,
                "lifecycle_stage": lifecycle_stage,
                "stock_count": len(stocks),
                "dt_seat_count": len(seats),
            }

            results.append(InstitutionStyleOutput(
                trade_date=td,
                subject_key=key,
                theme_name=name,
                institution_score=final_score,
                base_score=base_score,
                confidence=conf,
                market_regime_factor=round(market_regime_factor, 3),
                flow_score=round(flow_score, 2) if flow_score is not None else None,
                cycle_score=round(cycle_score, 2) if cycle_score is not None else None,
                structure_score=round(structure_score, 2) if structure_score is not None else None,
                dragon_tiger_score=round(dt_score, 2) if dt_score is not None else None,
                lifecycle_stage=lifecycle_stage,
                evidence_quality=evidence_quality,
                evidence=evidence,
                top_signals=top_signals[:6],
            ))

        return results


# ── S1: Fund Flow Score ──

def _compute_flow_score(flow: dict[str, Any]) -> tuple[float | None, str, list[str]]:
    """Compute flow_score from theme_capital_flow_daily row."""
    net = _float(flow.get("net_flow_yuan"))
    large = _float(flow.get("large_flow_yuan"))
    coverage = _float(flow.get("flow_coverage_ratio")) or 0.0

    if net is None:
        return None, "MISSING", []

    # Simulated 5-day history (single-day input in 33a; real 5d in future)
    # For now, use coverage as proxy for persistence signal
    persistence = min(1.0, coverage / 0.70)  # higher coverage → more stocks confirming
    acceleration = 0.5  # neutral baseline (needs 5d history)
    large_ratio = abs(large or 0.0) / max(abs(net), 1.0) if large else 0.0
    consistency = 0.5  # neutral baseline (needs 5d history)

    flow_score = (
        W_PERSISTENCE * persistence
        + W_ACCELERATION * acceleration
        + W_LARGE_RATIO * min(1.0, large_ratio)
        + W_CONSISTENCY * consistency
    )

    # Coverage penalty (data availability)
    if coverage < COVERAGE_THRESHOLD:
        flow_score *= coverage / COVERAGE_THRESHOLD

    # Theme depth penalty (single-stock themes are stock volatility, not theme flow)
    stock_count = max(1, int(flow.get("stock_count") or flow.get("attributed_stock_count") or 1))
    if stock_count <= 2:
        depth_factor = 0.55  # single/dual-stock: heavy penalty
    elif stock_count <= 5:
        depth_factor = 0.75  # narrow theme
    elif stock_count <= 10:
        depth_factor = 0.90  # medium breadth
    else:
        depth_factor = 1.00  # broad theme, no penalty
    flow_score *= depth_factor

    flow_score = round(min(1.0, max(0.0, flow_score)) * 100, 2)

    quality = "HIGH" if flow_score >= 70 else "MEDIUM" if flow_score >= 40 else "LOW"
    signals: list[str] = []
    if persistence > 0.7:
        signals.append("资金持续覆盖")
    if large_ratio > 0.4:
        signals.append("大资金主导")
    if coverage > 0.6:
        signals.append("覆盖率高")

    return flow_score, quality, signals


# ── S2: Cycle Score ──

def _compute_cycle_score(cycle: dict[str, Any]) -> tuple[float | None, str, list[str], str]:
    """Compute cycle_score from theme_cycle_judgement_v2 row."""
    stage = str(cycle.get("final_cycle_state") or cycle.get("stage") or "").strip().upper()
    prev_stage = str(cycle.get("previous_stage") or "").strip().upper()

    if not stage:
        return None, "MISSING", [], ""

    bonus = STAGE_BONUS.get(stage, DEFAULT_STAGE_BONUS)

    # Transition direction
    transition = 0.0
    if prev_stage:
        if stage in ("FERMENTATION", "INCUBATION"):
            transition = TRANSITION_UP
        elif stage == "DIFFUSION":
            transition = TRANSITION_UP_MILD
        elif stage in ("PEAK", "DISTRIBUTION"):
            transition = TRANSITION_DOWN
        elif stage == "DECAY":
            transition = TRANSITION_COLLAPSE

    cycle_score = round(min(1.0, max(0.0, bonus + transition)) * 100, 2)

    quality = "HIGH" if bonus >= 0.75 else "MEDIUM" if bonus >= 0.40 else "LOW"
    stage_label = stage.capitalize() if stage else ""
    signals: list[str] = [f"周期: {stage_label}"] if stage_label else []
    if transition > 0:
        signals.append("周期升级中")
    elif transition < 0:
        signals.append("周期降级中")

    return cycle_score, quality, signals, stage_label


# ── S3: Structure Score ──

def _compute_structure_score(stocks: list[dict[str, Any]]) -> tuple[float | None, str, list[str]]:
    """Compute structure_score from strong_stock_watch_history rows."""
    if not stocks:
        return None, "MISSING", []

    total = len(stocks)
    leaders = [s for s in stocks if str(s.get("role") or s.get("relay_role") or "").strip() == "龙头"]
    core = [s for s in stocks if str(s.get("role") or s.get("relay_role") or "").strip() == "中军"]
    positive = [s for s in stocks if (_float(s.get("watch_score")) or 0) > 0]

    leader_quality = (len([l for l in leaders if _float(l.get("watch_score") or 0) > 0]) / max(len(leaders), 1)) if leaders else 0.0
    core_strength = (len([c for c in core if _float(c.get("watch_score") or 0) > 0]) / max(len(core), 1)) if core else 0.0
    breadth = len(positive) / max(total, 1)

    structure_score = round((
        W_LEADER * leader_quality
        + W_CORE * core_strength
        + W_BREADTH * breadth
    ) * 100, 2)

    quality = "HIGH" if structure_score >= 70 else "MEDIUM" if structure_score >= 40 else "LOW"
    signals: list[str] = []
    if leaders:
        signals.append(f"龙头{len(leaders)}只")
    if core:
        signals.append(f"中军{len(core)}只")
    if breadth > 0.5:
        signals.append("板块扩散明显")

    return structure_score, quality, signals


# ── S4: Dragon Tiger Score ──

def _compute_dragon_tiger_score(seats: list[dict[str, Any]]) -> tuple[float | None, str, list[str]]:
    """Compute dragon_tiger_score from seat evidence rows."""
    if not seats:
        return None, "MISSING", []

    total_buy = 0.0
    weighted_buy = 0.0
    inst_buy = 0.0
    seat_count = 0

    for s in seats:
        seat_type = str(s.get("seat_type") or s.get("seat_name") or "")
        buy = _float(s.get("buy_amount") or s.get("net_buy")) or 0.0
        total_buy += abs(buy)
        quality = SEAT_QUALITY.get(seat_type, DEFAULT_SEAT_QUALITY)
        weighted_buy += abs(buy) * quality
        if seat_type == "机构专用":
            inst_buy += buy
        seat_count += 1

    seat_quality_weighted = weighted_buy / max(total_buy, 1.0)
    buy_intensity = inst_buy / max(total_buy, 1.0) if inst_buy > 0 else 0.0

    dt_score = round((0.60 * seat_quality_weighted + 0.40 * buy_intensity) * 100, 2)

    quality = "HIGH" if dt_score >= 70 else "MEDIUM" if dt_score >= 40 else "LOW"
    signals: list[str] = []
    if seat_count > 0:
        signals.append(f"机构席位{seat_count}个")
    if inst_buy > 0:
        signals.append("机构净买入")

    return dt_score, quality, signals


# ── Helpers ──

def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _trade_date_from(rows: list[dict[str, Any]]) -> date:
    for r in rows:
        td = r.get("trade_date")
        if td:
            if isinstance(td, date):
                return td
            text = str(td).strip()
            if len(text) == 8 and text.isdigit():
                return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
            return date.fromisoformat(text[:10])
    return date.today()
