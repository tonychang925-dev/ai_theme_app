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
    target_component: str                  # "emotion_formula" | "death_index" | "relay"
    current_weight: float
    proposed_weight: float
    delta: float
    rationale: str
    evidence_count: int                    # how many calibration points support this
    confidence: float                      # 0-1
    status: str = "proposed"               # proposed | accepted | rejected
    accepted_at: datetime | None = None


# ═══ Calibration Engine ═══

class CalibrationEngine:
    """Compare AI output against analyst reference and track drift."""

    def __init__(self):
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
