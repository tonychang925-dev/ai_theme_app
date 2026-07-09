"""M2.5 Phase 3.4 — Analyst Calibration Learning Loop.

Not just a dataset — a feedback system that measures AI↔Analyst drift,
attributes errors to root causes, and proposes weight adjustments for
human review (never auto-apply).

Architecture:
  Daily Snapshot → AI Diagnosis ──┐
                                  ├→ CalibrationEngine → DriftReport
  Analyst Reference ──────────────┘       │
                                          ├→ ErrorAttribution
                                          └→ WeightProposal (review required)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


# ═══ Analyst Reference Dataset ═══

@dataclass
class AnalystReferenceRecord:
    """One trading day's analyst ground truth."""
    trade_date: date

    # L0: Market Facts
    limit_up_count: int | None = None
    max_board_height: int | None = None
    sealed_ratio: float | None = None
    relay_1_to_2: float | None = None
    relay_2_to_3: float | None = None
    loss_count: int | None = None         # 跌停数
    active_capital_yi: float | None = None

    # L1: Market Cognition
    market_phase: str = ""                 # PANIC / FREEZE / DISTRIBUTION / ...
    risk_level: str = ""                   # LOW / MEDIUM / HIGH / CRITICAL
    strategy: str = ""                     # analyst's strategy text
    emotion_momentum: float | None = None  # analyst's emotion score (-12 etc.)

    # Meta
    source: str = "analyst_pdf"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date.isoformat(),
            "facts": {
                "limit_up": self.limit_up_count,
                "max_board": self.max_board_height,
                "sealed_ratio": self.sealed_ratio,
                "relay_1_2": self.relay_1_to_2,
                "relay_2_3": self.relay_2_to_3,
                "loss_count": self.loss_count,
                "active_capital_yi": self.active_capital_yi,
            },
            "cognition": {
                "phase": self.market_phase,
                "risk": self.risk_level,
                "strategy": self.strategy,
                "emotion": self.emotion_momentum,
            },
            "source": self.source,
        }


# ═══ Error Type Classification ═══

class DriftType:
    UNDER_REACTION = "UNDER_REACTION"
    OVER_REACTION = "OVER_REACTION"
    TIMING_ERROR = "TIMING_ERROR"
    DATA_ERROR = "DATA_ERROR"
    SEMANTIC_ERROR = "SEMANTIC_ERROR"
    PRIORITY_ERROR = "PRIORITY_ERROR"        # saw data, focused on wrong variable


# ═══ Calibration Config ═══

@dataclass
class CalibrationConfig:
    window_days: int = 60
    min_samples: int = 20
    confidence_threshold: float = 0.75
    min_similar_errors: int = 5


# ═══ Metric Drift ═══

@dataclass
class MetricDrift:
    """A single metric's deviation from analyst reference."""
    metric_name: str
    ai_value: float
    analyst_value: float
    drift: float                           # ai - analyst
    drift_pct: float                       # relative to analyst value
    direction: str                         # OVER_OPTIMISTIC | OVER_PESSIMISTIC | MATCH
    severity: str                          # CRITICAL | SIGNIFICANT | MINOR | NONE
    likely_cause: str = ""                 # attribution hypothesis


@dataclass
class DriftReport:
    """Aggregate drift analysis for one trading day."""
    trade_date: date
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    drifts: list[MetricDrift] = field(default_factory=list)

    over_optimistic_count: int = 0
    over_pessimistic_count: int = 0
    match_count: int = 0

    overall_bias: str = ""                 # OPTIMISTIC | PESSIMISTIC | BALANCED
    critical_drifts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date.isoformat(),
            "overall_bias": self.overall_bias,
            "drifts": [{
                "metric": d.metric_name, "ai": d.ai_value, "analyst": d.analyst_value,
                "drift": d.drift, "direction": d.direction, "severity": d.severity,
                "likely_cause": d.likely_cause,
            } for d in self.drifts],
            "critical": self.critical_drifts,
        }


# ═══ Weight Proposal ═══

@dataclass
class WeightProposal:
    """Suggested weight adjustment — NEVER auto-apply."""
    target_component: str
    current_weight: float
    proposed_weight: float
    delta: float
    rationale: str
    evidence_count: int
    confidence: float
    # v2: evidence with cases
    supporting_cases: list[str] = field(default_factory=list)   # dates that support
    counter_cases: list[str] = field(default_factory=list)      # dates that contradict
    expected_gain: str = ""              # "PANIC recall +18%"
    error_type: str = ""                 # DriftType classification
    status: str = "proposed"
    accepted_at: datetime | None = None


# ═══ Calibration Engine ═══

class CalibrationEngine:
    """Compare AI output against analyst reference and track drift."""

    def __init__(self, config: CalibrationConfig | None = None):
        self.config = config or CalibrationConfig()
        self._references: dict[date, AnalystReferenceRecord] = {}
        self._drift_history: list[DriftReport] = []
        self._proposals: list[WeightProposal] = []

    def add_reference(self, ref: AnalystReferenceRecord) -> None:
        self._references[ref.trade_date] = ref

    def compute_drift(self, trade_date: date, ai_facts: dict, ai_phase: str,
                       ai_risk: str, ai_emotion: float) -> DriftReport | None:
        """Compare AI output with analyst reference for one trading day."""
        ref = self._references.get(trade_date)
        if not ref:
            return None

        drifts: list[MetricDrift] = []

        def _add_drift(name: str, ai_val: float | None, ref_val: float | None):
            if ai_val is None or ref_val is None or ref_val == 0:
                return
            d = ai_val - ref_val
            pct = abs(d) / abs(ref_val)
            if pct < 0.05:
                direction, severity = "MATCH", "NONE"
            elif d > 0:
                direction = "OVER_OPTIMISTIC" if "emotion" not in name else "OVER_OPTIMISTIC"
                severity = "CRITICAL" if pct > 0.5 else ("SIGNIFICANT" if pct > 0.2 else "MINOR")
            else:
                direction = "OVER_PESSIMISTIC"
                severity = "CRITICAL" if pct > 0.5 else ("SIGNIFICANT" if pct > 0.2 else "MINOR")
            drifts.append(MetricDrift(
                metric_name=name, ai_value=ai_val, analyst_value=ref_val,
                drift=d, drift_pct=round(pct, 3), direction=direction, severity=severity,
                likely_cause=self._attribute_cause(name, d, direction),
            ))

        _add_drift("limit_up_count", ai_facts.get("limit_up"), ref.limit_up_count)
        _add_drift("max_board_height", ai_facts.get("max_board"), ref.max_board_height)
        _add_drift("relay_1_to_2", ai_facts.get("relay_1_2"), ref.relay_1_to_2)
        _add_drift("emotion_momentum", ai_emotion, ref.emotion_momentum)

        opt = sum(1 for d in drifts if d.direction == "OVER_OPTIMISTIC")
        pes = sum(1 for d in drifts if d.direction == "OVER_PESSIMISTIC")
        mat = sum(1 for d in drifts if d.direction == "MATCH")

        if opt > pes + 1:     bias = "OPTIMISTIC"
        elif pes > opt + 1:   bias = "PESSIMISTIC"
        else:                 bias = "BALANCED"

        critical = [d.metric_name for d in drifts if d.severity == "CRITICAL"]

        report = DriftReport(
            trade_date=trade_date, drifts=drifts,
            over_optimistic_count=opt, over_pessimistic_count=pes,
            match_count=mat, overall_bias=bias, critical_drifts=critical,
        )
        self._drift_history.append(report)
        return report

    @staticmethod
    def _attribute_cause(metric: str, drift: float, direction: str) -> str:
        causes = {
            "emotion_momentum": "loss_weight不足" if direction == "OVER_OPTIMISTIC" else "loss_weight过重",
            "limit_up_count": "涨停统计口径差异",
            "max_board_height": "最高板定义不同(streak回溯深度)",
            "relay_1_to_2": "晋级率计算窗口不一致",
        }
        return causes.get(metric, "待分析")

    def propose_weights(self, min_evidence: int = 5) -> list[WeightProposal]:
        """Generate weight adjustment proposals from drift history."""
        proposals: list[WeightProposal] = []
        if len(self._drift_history) < min_evidence:
            return proposals

        # Count emotion over-optimistic cases
        emo_opt = sum(1 for r in self._drift_history
                      for d in r.drifts
                      if d.metric_name == "emotion_momentum" and d.direction == "OVER_OPTIMISTIC")
        emo_total = sum(1 for r in self._drift_history
                        for d in r.drifts if d.metric_name == "emotion_momentum")

        if emo_total >= min_evidence and emo_opt > emo_total * 0.6:
            proposals.append(WeightProposal(
                target_component="emotion_formula.loss_weight",
                current_weight=0.20, proposed_weight=0.25, delta=0.05,
                rationale=f"过去{emo_total}次校准中{emo_opt}次情绪偏乐观，建议提升loss权重从20%→25%",
                evidence_count=emo_total, confidence=round(emo_opt / emo_total, 2),
            ))

        # Check relay_1_to_2 drift
        relay_drifts = [d for r in self._drift_history
                        for d in r.drifts if d.metric_name == "relay_1_to_2"]
        relay_off = sum(1 for d in relay_drifts if d.severity in ("CRITICAL", "SIGNIFICANT"))
        if len(relay_drifts) >= min_evidence and relay_off > len(relay_drifts) * 0.5:
            proposals.append(WeightProposal(
                target_component="relay_calculation",
                current_weight=0, proposed_weight=0, delta=0,
                rationale=f"晋级率计算持续偏差({relay_off}/{len(relay_drifts)})，建议升级为relay_ecology_daily表直接JOIN",
                evidence_count=len(relay_drifts), confidence=round(relay_off / len(relay_drifts), 2),
            ))

        self._proposals = proposals
        return proposals

    def accept_proposal(self, index: int) -> None:
        if 0 <= index < len(self._proposals):
            self._proposals[index].status = "accepted"
            self._proposals[index].accepted_at = datetime.now(timezone.utc)

    def reject_proposal(self, index: int) -> None:
        if 0 <= index < len(self._proposals):
            self._proposals[index].status = "rejected"

    def dashboard(self) -> dict:
        """Generate Calibration Dashboard summary."""
        n = len(self._drift_history)
        if n == 0:
            return {"status": "no_data", "total_calibrations": 0}

        # Phase accuracy
        phases: dict[str, dict] = {}
        for r in self._drift_history:
            for d in r.drifts:
                if d.metric_name == "emotion_momentum":
                    bucket = "match" if d.severity == "NONE" else d.direction
                    phases.setdefault("emotion", {"total": 0, "match": 0, "opt": 0, "pes": 0})
                    phases["emotion"]["total"] += 1
                    if d.severity == "NONE": phases["emotion"]["match"] += 1
                    elif d.direction == "OVER_OPTIMISTIC": phases["emotion"]["opt"] += 1
                    else: phases["emotion"]["pes"] += 1

        # Error attribution
        error_counts: dict[str, int] = {}
        for r in self._drift_history:
            for d in r.drifts:
                if d.severity in ("CRITICAL", "SIGNIFICANT"):
                    cause = d.likely_cause or "unknown"
                    error_counts[cause] = error_counts.get(cause, 0) + 1

        total_errors = sum(error_counts.values())
        error_pct = {k: round(v / max(total_errors, 1) * 100, 1) for k, v in error_counts.items()}

        # Overall bias trend
        bias_counts = {"OPTIMISTIC": 0, "PESSIMISTIC": 0, "BALANCED": 0}
        for r in self._drift_history:
            bias_counts[r.overall_bias] = bias_counts.get(r.overall_bias, 0) + 1

        return {
            "total_calibrations": n,
            "config": {
                "window_days": self.config.window_days,
                "min_samples": self.config.min_samples,
                "confidence_threshold": self.config.confidence_threshold,
            },
            "phase_accuracy": {
                k: {"accuracy": round(v["match"] / max(v["total"], 1) * 100, 1)}
                for k, v in phases.items()
            },
            "error_attribution": error_pct,
            "bias_trend": bias_counts,
            "pending_proposals": len([p for p in self._proposals if p.status == "proposed"]),
            "accepted_proposals": len([p for p in self._proposals if p.status == "accepted"]),
            "recent_drifts": [r.to_dict() for r in self._drift_history[-5:]],
        }


# ═══ Policy Versioning ═══

@dataclass
class PolicyVersion:
    """Immutable snapshot of the full cognition policy at a point in time."""
    version: str                           # "M8_POLICY_v1"
    created_at: datetime
    emotion_formula: str                   # "v4.1"
    death_index_version: str               # "v2"
    propagation_version: str               # "v2"
    relay_version: str                     # "v2"
    weights: dict[str, float] = field(default_factory=dict)
    notes: str = ""


# ═══ Proposal Simulator ═══

@dataclass
class SimulatorResult:
    proposal: WeightProposal
    before_recall: float          # recall with old weight
    after_recall: float           # recall with new weight (simulated)
    false_positive_change: float  # +X% false alarms from weight change
    net_benefit: str              # "POSITIVE" | "NEUTRAL" | "NEGATIVE"
    recommendation: str           # "建议接受" | "建议拒绝" | "需更多数据"


class ProposalSimulator:
    """Simulate weight changes against historical data before approving."""

    @staticmethod
    def simulate(proposal: WeightProposal,
                 history_days: int = 60) -> SimulatorResult:
        """Run what-if simulation for a weight proposal.

        Currently uses heuristics based on evidence_count and confidence.
        Future: actual backtest against historical replay cache.
        """
        # Heuristic simulation
        before = round(proposal.confidence * 0.8, 2)  # approximate recall
        after = round(min(1.0, before + abs(proposal.delta) * 2), 2)
        fp_change = round(abs(proposal.delta) * 1.5 * 100, 1)  # % increase in false positives

        if after - before > 0.1 and fp_change < 15:
            benefit = "POSITIVE"
            rec = "建议接受"
        elif after - before > 0.05:
            benefit = "NEUTRAL"
            rec = "需更多数据"
        else:
            benefit = "NEGATIVE"
            rec = "建议拒绝"

        return SimulatorResult(
            proposal=proposal, before_recall=before, after_recall=after,
            false_positive_change=fp_change, net_benefit=benefit,
            recommendation=rec)


# ═══ Analyst Turing Score ═══

def compute_turing_score(phase_accuracy: float, risk_accuracy: float,
                          evidence_alignment: float, strategy_alignment: float) -> dict:
    """Analyst Turing Score: how close is AI cognition to a real analyst?

    NOT prediction accuracy. This measures cognitive alignment:
      40% Market Phase Agreement
      25% Risk Agreement
      20% Key Evidence Agreement
      15% Strategy Agreement
    """
    score = round(
        phase_accuracy * 0.40 + risk_accuracy * 0.25
        + evidence_alignment * 0.20 + strategy_alignment * 0.15, 1)

    if score >= 85:   level = "EXPERT"       # indistinguishable from analyst
    elif score >= 70: level = "SENIOR"        # close to analyst
    elif score >= 55: level = "JUNIOR"        # basic alignment
    elif score >= 40: level = "TRAINEE"       # significant gaps
    else:             level = "NOVICE"        # fundamental differences

    return {
        "turing_score": score, "level": level,
        "components": {
            "phase_agreement": phase_accuracy,
            "risk_agreement": risk_accuracy,
            "evidence_alignment": evidence_alignment,
            "strategy_alignment": strategy_alignment,
        },
    }


# ═══ Cognitive Evolution Report ═══

@dataclass
class EvolutionReport:
    policy_version: str
    total_days: int
    top_errors: list[dict]
    weight_changes: list[dict]
    improvement_summary: str

    # v2: Cognitive Improvement
    cognitive_trend: list[dict] = field(default_factory=list)
    # [{version: "v1", phase_acc: 63, risk_acc: 70, turing: 58}, ...]

    # v2: Blind Spot Analysis
    blind_spots: list[dict] = field(default_factory=list)
    # [{pattern: "高位死亡低估", occurrences: 12, pct: 42, severity: "CRITICAL"}]

    # v2: Analyst Gap Score
    gap_score: dict = field(default_factory=dict)
    # {phase: 92, risk: 85, strategy: 70, overall: 84, trend: "↑"}

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "policy_version": self.policy_version,
            "total_days": self.total_days,
            "top_errors": self.top_errors,
            "weight_changes": self.weight_changes,
            "improvement_summary": self.improvement_summary,
            "cognitive_trend": self.cognitive_trend,
            "blind_spots": self.blind_spots,
            "gap_score": self.gap_score,
        }


def build_evolution_report(engine: CalibrationEngine,
                           phase_acc: float = 0.0, risk_acc: float = 0.0,
                           strategy_acc: float = 0.0,
                           prev_scores: list[dict] | None = None) -> EvolutionReport:
    """Generate cognitive evolution report v2 with all dimensions."""
    drifts = engine._drift_history
    n = len(drifts)

    # ── Error attribution ──
    cause_counts: dict[str, int] = {}
    for r in drifts:
        for d in r.drifts:
            if d.severity in ("CRITICAL", "SIGNIFICANT"):
                cause_counts[d.likely_cause] = cause_counts.get(d.likely_cause, 0) + 1

    total = sum(cause_counts.values()) or 1
    top_errors = sorted(
        [{"cause": k, "pct": round(v / total * 100, 1),
          "action": _suggest_action(k)} for k, v in cause_counts.items()],
        key=lambda x: -x["pct"])[:3]

    changes = [{
        "component": p.target_component,
        "old": p.current_weight, "new": p.proposed_weight,
        "reason": p.rationale[:60],
    } for p in engine._proposals if p.status == "accepted"]

    summary = (f"过去{n}天，AI最大错误来源：{top_errors[0]['cause']}({top_errors[0]['pct']}%)。"
               if top_errors else "暂无足够校准数据。")

    # ── v2: Cognitive Improvement Trend ──
    trend = list(prev_scores or [])
    turing = compute_turing_score(phase_acc, risk_acc, 0.0, strategy_acc)
    trend.append({
        "version": f"v{len(trend) + 1}",
        "phase_acc": phase_acc, "risk_acc": risk_acc,
        "strategy_acc": strategy_acc, "turing": turing["turing_score"],
    })

    # ── v2: Blind Spot Analysis ──
    # Persistent patterns: errors that appear >=3 times AND >=20% of total
    blind_spots = sorted(
        [{"pattern": k, "occurrences": v, "pct": round(v / total * 100, 1),
          "severity": "CRITICAL" if v >= 5 else "MODERATE"}
         for k, v in cause_counts.items() if v >= 2],
        key=lambda x: -x["occurrences"])[:3]

    # Characterize AI's "personality flaw"
    if blind_spots:
        top_blind = blind_spots[0]
        top_blind["personality_note"] = (
            f"AI的'性格缺陷'：{top_blind['pattern']}"
            f"（出现{top_blind['occurrences']}次，占{top_blind['pct']}%）。"
            f"这类似一个'过于关注市场宽度而忽略高位风险'的分析师。"
        )

    # ── v2: Analyst Gap Score ──
    gap = {
        "phase": round(phase_acc, 1),
        "risk": round(risk_acc, 1),
        "strategy": round(strategy_acc, 1),
        "overall": round((phase_acc + risk_acc + strategy_acc) / 3, 1),
        "turing_score": turing["turing_score"],
        "turing_level": turing["level"],
    }
    # Trend direction
    prev_avg = sum(s.get("turing", 0) for s in (prev_scores or [])) / max(len(prev_scores or []), 1)
    if turing["turing_score"] > prev_avg + 3:
        gap["trend"] = "↑ 持续改善"
    elif turing["turing_score"] < prev_avg - 3:
        gap["trend"] = "↓ 需要关注"
    else:
        gap["trend"] = "→ 稳定"

    return EvolutionReport(
        policy_version="M8_POLICY_v1",
        total_days=n, top_errors=top_errors,
        weight_changes=changes, improvement_summary=summary,
        cognitive_trend=trend, blind_spots=blind_spots, gap_score=gap)


def _suggest_action(cause: str) -> str:
    return {
        "loss_weight不足": "Death weight +5%, Breadth weight -5%",
        "loss_weight过重": "Death weight -5%",
        "涨停统计口径差异": "统一涨停统计口径",
        "最高板定义不同(streak回溯深度)": "限制streak回溯深度为2日",
        "晋级率计算窗口不一致": "升级为relay_ecology_daily表JOIN",
    }.get(cause, "待分析")


# ═══ Pre-built 7/7 reference ═══

def build_20260707_calibration_ref() -> AnalystReferenceRecord:
    return AnalystReferenceRecord(
        trade_date=date(2026, 7, 7),
        limit_up_count=33, max_board_height=5,
        relay_1_to_2=0.051, relay_2_to_3=0.0,
        loss_count=83, active_capital_yi=897.0,
        market_phase="PANIC", risk_level="HIGH",
        strategy="等待修复，观察新题材",
        emotion_momentum=-12.0,
        source="analyst_pdf", notes="DeepSeek结构化版 7月7日复盘",
    )
