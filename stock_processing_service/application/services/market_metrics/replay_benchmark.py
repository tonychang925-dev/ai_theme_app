"""M2.5 Phase 3.4 — Historical Replay Benchmark.

Validates AI market understanding against analyst reference across
key historical dates. Measures not just accuracy but alignment.

Scoring framework (100 points):
  L0 — Market Fact Accuracy (50pts): basic numbers match
  L1 — Market State Recognition (25pts): phase/emotion match
  L2 — Risk Recognition (15pts): death index + risk level match
  L3 — Strategy Alignment (10pts): allowed/forbidden actions match

The goal is NOT prediction accuracy — it's analyst alignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from .contracts import MarketMetricsSnapshot


# ═══ Benchmark Case ═══

@dataclass
class AnalystReference:
    """Ground truth from analyst PDF for one trading day."""
    trade_date: date

    # L0: Market facts
    limit_up_count: int | None = None
    turnover_wan_yi: float | None = None    # 万亿
    max_board_height: int | None = None

    # L1: Market state
    market_phase: str = ""                   # e.g. "PANIC", "退潮", "冰点"
    phase_confidence: float = 1.0            # analyst's own confidence

    # L2: Risk
    risk_level: str = ""                     # LOW/MEDIUM/HIGH/CRITICAL
    death_signal: str = ""                   # e.g. "龙头断板3只"
    key_concern: str = ""                    # analyst's main worry

    # L3: Strategy
    strategy: str = ""                       # analyst's strategy description
    forbidden: str = ""                      # comma-separated forbidden actions

    # Meta
    analyst_notes: str = ""                  # raw text from PDF for reference
    source: str = ""                         # "analyst_pdf" | "manual"


@dataclass
class AlignmentScores:
    """Per-dimension alignment between AI and analyst."""
    # L0: Fact accuracy (0-50)
    l0_limitup_score: float = 0     # 10pts
    l0_turnover_score: float = 0    # 10pts
    l0_height_score: float = 0      # 10pts
    l0_relay_score: float = 0       # 10pts
    l0_sealed_score: float = 0      # 10pts
    l0_total: float = 0

    # L1: State recognition (0-25)
    l1_phase_match: bool = False
    l1_phase_score: float = 0       # 25pts or partial
    l1_total: float = 0

    # L2: Risk recognition (0-15)
    l2_risk_match: bool = False
    l2_death_detected: bool = False
    l2_risk_score: float = 0        # 15pts
    l2_total: float = 0

    # L3: Strategy alignment (0-10)
    l3_strategy_aligned: bool = False
    l3_strategy_score: float = 0    # 10pts
    l3_total: float = 0

    # Overall
    overall: float = 0               # 0-100
    grade: str = ""                  # A/B/C/D/F

    # Explainability
    match_details: list[str] = field(default_factory=list)
    mismatch_details: list[str] = field(default_factory=list)


@dataclass
class ReplayResult:
    """Result of replaying one trading day."""
    trade_date: date
    reference: AnalystReference
    snapshot: dict[str, Any] = field(default_factory=dict)
    ai_phase: str = ""
    ai_risk: str = ""
    ai_death_label: str = ""
    ai_death_index: float = 0.0
    ai_strategy: str = ""
    ai_headline: str = ""
    scores: AlignmentScores = field(default_factory=AlignmentScores)
    explain: str = ""


@dataclass
class ReplayReport:
    """Aggregate benchmark report across all replay cases."""
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    results: list[ReplayResult] = field(default_factory=list)
    total_cases: int = 0
    avg_overall: float = 0.0
    avg_l0: float = 0.0
    avg_l1: float = 0.0
    avg_l2: float = 0.0
    avg_l3: float = 0.0
    phase_accuracy: float = 0.0       # % of phase matches
    risk_accuracy: float = 0.0        # % of risk matches
    grade_distribution: dict[str, int] = field(default_factory=dict)
    key_findings: list[str] = field(default_factory=list)
    improvement_areas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "total_cases": self.total_cases,
            "avg_scores": {
                "overall": self.avg_overall, "l0_facts": self.avg_l0,
                "l1_state": self.avg_l1, "l2_risk": self.avg_l2,
                "l3_strategy": self.avg_l3,
            },
            "phase_accuracy": self.phase_accuracy,
            "risk_accuracy": self.risk_accuracy,
            "grade_distribution": self.grade_distribution,
            "key_findings": self.key_findings,
            "improvement_areas": self.improvement_areas,
            "results": [{
                "date": r.trade_date.isoformat(),
                "ai_phase": r.ai_phase, "ref_phase": r.reference.market_phase,
                "ai_risk": r.ai_risk, "ref_risk": r.reference.risk_level,
                "ai_death": f"{r.ai_death_label}({r.ai_death_index:.0f})",
                "overall": r.scores.overall, "grade": r.scores.grade,
                "explain": r.explain,
            } for r in self.results],
        }


# ═══ Phase mapping: AI ontology → analyst vocabulary ═══

PHASE_TO_ANALYST = {
    "START":            "启动",
    "FERMENTATION":     "发酵",
    "ACCELERATION":     "加速",
    "CLIMAX":           "高潮",
    "REPAIR":           "修复",
    "FIRST_DIVERGENCE": "第一次分歧",
    "DISTRIBUTION":     "高位派发",
    "PANIC":            "恐慌释放",
    "FREEZE":           "情绪冰点",
}

# Analyst keywords → AI phase (reverse mapping for comparison)
ANALYST_KEYWORDS = {
    "PANIC":            ["恐慌", "恐慌释放", "情绪恐慌"],
    "FREEZE":           ["冰点", "情绪冰点", "极致冰点", "冻结"],
    "DISTRIBUTION":     ["退潮", "派发", "高位退潮", "补跌"],
    "FIRST_DIVERGENCE": ["分歧", "第一次分歧", "高位分歧"],
    "REPAIR":           ["修复", "反弹", "回暖", "情绪修复"],
    "CLIMAX":           ["高潮", "加速高潮", "亢奋"],
    "ACCELERATION":     ["加速", "主升"],
}


# ═══ Replay Engine ═══

class ReplayEngine:
    """Run historical replay and score AI vs analyst alignment."""

    def __init__(self):
        self._reference_cases: dict[date, AnalystReference] = {}

    def add_reference(self, ref: AnalystReference) -> None:
        self._reference_cases[ref.trade_date] = ref

    def score_one(self, snap: MarketMetricsSnapshot,
                  narrative: Any = None) -> ReplayResult:
        """Score AI output against analyst reference for one trading day."""
        ref = self._reference_cases.get(snap.trade_date)
        if ref is None:
            return ReplayResult(trade_date=snap.trade_date,
                               reference=AnalystReference(snap.trade_date),
                               explain="No analyst reference for this date.")

        b = snap.breadth
        l = snap.limitup
        r = snap.relay
        leader = snap.leader_evolution
        death = snap.high_position_death
        loss = snap.loss_effect

        scores = AlignmentScores()
        matches = []
        mismatches = []

        # ═══ L0: Market Fact Accuracy (50pts) ═══
        if ref.limit_up_count is not None:
            diff = abs(l.total_count - ref.limit_up_count)
            if diff == 0:
                scores.l0_limitup_score = 10
                matches.append(f"涨停数精确匹配: {l.total_count}")
            elif diff <= 3:
                scores.l0_limitup_score = 8
                mismatches.append(f"涨停数偏差{diff}: AI={l.total_count}, 分析师={ref.limit_up_count}")
            elif diff <= 10:
                scores.l0_limitup_score = 4
                mismatches.append(f"涨停数偏差较大{diff}: AI={l.total_count}, 分析师={ref.limit_up_count}")
            else:
                mismatches.append(f"涨停数严重偏差{diff}: AI={l.total_count}, 分析师={ref.limit_up_count}")

        if ref.turnover_wan_yi is not None:
            ai_turnover = b.turnover_yi / 10000  # 亿 → 万亿
            diff_pct = abs(ai_turnover - ref.turnover_wan_yi) / max(ref.turnover_wan_yi, 0.01)
            if diff_pct < 0.05:
                scores.l0_turnover_score = 10
                matches.append(f"成交额匹配: {ai_turnover:.1f}万亿")
            elif diff_pct < 0.15:
                scores.l0_turnover_score = 7
            else:
                scores.l0_turnover_score = 3

        if ref.max_board_height is not None:
            diff = abs(l.max_board_height - ref.max_board_height)
            if diff == 0:
                scores.l0_height_score = 10
            elif diff <= 1:
                scores.l0_height_score = 7
            else:
                scores.l0_height_score = 3

        # Relay + sealed (10pts each)
        scores.l0_relay_score = 8 if r.promotion_1_to_2 > 0 else 5
        scores.l0_sealed_score = 8 if l.sealed_board_ratio > 0 else 5

        scores.l0_total = (scores.l0_limitup_score + scores.l0_turnover_score
                          + scores.l0_height_score + scores.l0_relay_score
                          + scores.l0_sealed_score)
        scores.l0_total = min(50, scores.l0_total)

        # ═══ L1: Market State Recognition (25pts) ═══
        ai_phase = narrative.market_phase if narrative else self._infer_phase(r, death)
        ai_phase_analyst = PHASE_TO_ANALYST.get(ai_phase, ai_phase)

        ref_phase = ref.market_phase
        # Try to map analyst phase to AI phase
        ref_mapped = None
        for ai_p, keywords in ANALYST_KEYWORDS.items():
            if any(kw in ref_phase for kw in keywords):
                ref_mapped = ai_p
                break

        if ref_mapped and ai_phase == ref_mapped:
            scores.l1_phase_match = True
            scores.l1_phase_score = 25
            matches.append(f"市场阶段精确匹配: {ai_phase_analyst}")
        elif ref_mapped:
            # Partial credit: same bucket group
            panic_group = {"PANIC", "FREEZE"}
            diverge_group = {"FIRST_DIVERGENCE", "DISTRIBUTION"}
            climax_group = {"CLIMAX", "ACCELERATION"}
            repair_group = {"REPAIR", "FERMENTATION", "START"}

            for group in [panic_group, diverge_group, climax_group, repair_group]:
                if ai_phase in group and ref_mapped in group:
                    scores.l1_phase_score = 15
                    matches.append(f"市场阶段同组匹配: AI={ai_phase_analyst}, 分析师={ref_phase}")
                    break
            else:
                scores.l1_phase_score = 5
                mismatches.append(f"市场阶段不匹配: AI={ai_phase_analyst}, 分析师={ref_phase}")
        else:
            scores.l1_phase_score = 10  # can't verify

        scores.l1_total = scores.l1_phase_score

        # ═══ L2: Risk Recognition (15pts) ═══
        ai_risk = narrative.risk_level if narrative else "MEDIUM"
        if death and death.death_label in ("CRITICAL", "DANGER"):
            scores.l2_death_detected = True

        if ref.risk_level:
            if ai_risk == ref.risk_level:
                scores.l2_risk_match = True
                scores.l2_risk_score = 15
                matches.append(f"风险等级匹配: {ai_risk}")
            elif ai_risk == "CRITICAL" and ref.risk_level == "HIGH":
                scores.l2_risk_score = 12  # AI slightly more conservative
                mismatches.append(f"风险等级偏差: AI={ai_risk}(偏保守), 分析师={ref.risk_level}")
            elif ai_risk == "HIGH" and ref.risk_level == "CRITICAL":
                scores.l2_risk_score = 8   # AI underestimated
                mismatches.append(f"风险等级偏差: AI={ai_risk}(低估), 分析师={ref.risk_level}")
            else:
                scores.l2_risk_score = 4
                mismatches.append(f"风险等级严重偏差: AI={ai_risk}, 分析师={ref.risk_level}")
        else:
            scores.l2_risk_score = 8  # no reference to compare

        scores.l2_total = scores.l2_risk_score

        # ═══ L3: Strategy Alignment (10pts) ═══
        ai_strategy = narrative.strategy_summary if narrative else ""
        if ref.strategy:
            # Check keyword overlap
            ai_keywords = set(ai_strategy) if ai_strategy else set()
            ref_keywords = set(ref.strategy)
            overlap = len(ai_keywords & ref_keywords) / max(len(ref_keywords), 1)
            if overlap > 0.5:
                scores.l3_strategy_aligned = True
                scores.l3_strategy_score = 10
            elif overlap > 0.2:
                scores.l3_strategy_score = 6
            else:
                scores.l3_strategy_score = 3
        else:
            scores.l3_strategy_score = 7  # no reference

        scores.l3_total = scores.l3_strategy_score

        # ═══ Overall ═══
        scores.overall = scores.l0_total + scores.l1_total + scores.l2_total + scores.l3_total
        if scores.overall >= 85:    scores.grade = "A"
        elif scores.overall >= 70:  scores.grade = "B"
        elif scores.overall >= 55:  scores.grade = "C"
        elif scores.overall >= 40:  scores.grade = "D"
        else:                       scores.grade = "F"

        scores.match_details = matches
        scores.mismatch_details = mismatches

        # Build explainability
        explain_parts = []
        if matches:
            explain_parts.append("✓ " + "; ".join(matches[:3]))
        if mismatches:
            explain_parts.append("✗ " + "; ".join(mismatches[:3]))

        return ReplayResult(
            trade_date=snap.trade_date,
            reference=ref,
            snapshot={"lu": l.total_count, "sealed": l.sealed_board_ratio,
                      "max_h": l.max_board_height, "turnover": b.turnover_yi,
                      "death": death.death_label if death else "N/A",
                      "feedback": r.feedback_score},
            ai_phase=ai_phase,
            ai_risk=ai_risk,
            ai_death_label=death.death_label if death else "N/A",
            ai_death_index=death.death_index if death else 0,
            ai_strategy=ai_strategy,
            ai_headline=narrative.headline if narrative else "",
            scores=scores,
            explain=" | ".join(explain_parts),
        )

    def build_report(self, results: list[ReplayResult]) -> ReplayReport:
        """Aggregate results into a benchmark report."""
        n = len(results)
        if n == 0:
            return ReplayReport()

        avg_overall = round(sum(r.scores.overall for r in results) / n, 1)
        avg_l0 = round(sum(r.scores.l0_total for r in results) / n, 1)
        avg_l1 = round(sum(r.scores.l1_total for r in results) / n, 1)
        avg_l2 = round(sum(r.scores.l2_total for r in results) / n, 1)
        avg_l3 = round(sum(r.scores.l3_total for r in results) / n, 1)

        phase_match = sum(1 for r in results if r.scores.l1_phase_match)
        risk_match = sum(1 for r in results if r.scores.l2_risk_match)
        phase_acc = round(phase_match / n * 100, 1)
        risk_acc = round(risk_match / n * 100, 1)

        grades: dict[str, int] = {}
        for r in results:
            grades[r.scores.grade] = grades.get(r.scores.grade, 0) + 1

        findings = []
        if phase_acc >= 80:
            findings.append(f"市场阶段识别准确率{phase_acc}% — 优秀")
        elif phase_acc >= 60:
            findings.append(f"市场阶段识别{phase_acc}% — 需提升分歧/冰点区分")
        else:
            findings.append(f"市场阶段识别仅{phase_acc}% — 需校准ontology")

        if avg_l2 >= 12:
            findings.append("风险识别良好，death_index信号有效")
        elif avg_l2 >= 8:
            findings.append("风险识别中等，需增强loss effect权重")
        else:
            findings.append("风险识别偏弱，AI低估市场风险")

        improvements = []
        if phase_acc < 70:
            improvements.append("提升PANIC vs FREEZE区分能力")
        if avg_l2 < 10:
            improvements.append("增加高位死亡信号的权重")
        if avg_l3 < 7:
            improvements.append("策略生成需要更贴近分析师语言")

        return ReplayReport(
            results=results, total_cases=n,
            avg_overall=avg_overall, avg_l0=avg_l0, avg_l1=avg_l1,
            avg_l2=avg_l2, avg_l3=avg_l3,
            phase_accuracy=phase_acc, risk_accuracy=risk_acc,
            grade_distribution=grades,
            key_findings=findings, improvement_areas=improvements,
        )

    @staticmethod
    def _infer_phase(r, death) -> str:
        fb = r.feedback_score
        if death and death.death_label == "CRITICAL":
            return "PANIC"
        if fb < -50:    return "FREEZE"
        if fb < -20:    return "DISTRIBUTION"
        if fb < -5:     return "FIRST_DIVERGENCE"
        if fb < 10:     return "REPAIR"
        if fb < 30:     return "FERMENTATION"
        if fb < 50:     return "ACCELERATION"
        return "CLIMAX"


# ═══ Pre-built reference cases ═══

def build_20260707_reference() -> AnalystReference:
    """7/7 analyst reference from PDF."""
    return AnalystReference(
        trade_date=date(2026, 7, 7),
        limit_up_count=33,
        turnover_wan_yi=2.56,
        market_phase="情绪冰点",
        risk_level="CRITICAL",
        death_signal="高位科技补跌，涨停家数骤降",
        key_concern="高位核心是否继续退潮",
        strategy="防守等待，禁止高位接力，观察新方向首板",
        forbidden="高位接力,追龙头,重仓",
        analyst_notes="情绪冰点。涨停33家。高位科技补跌。等待修复。",
        source="analyst_pdf",
    )
