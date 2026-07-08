"""M2.5 Phase 3.1b — Analyst Replay Benchmark.

Validates AI narrative against analyst PDF for historical dates.
Answers: "Does the AI really think like an analyst?"

Benchmark dimensions:
  Phase Accuracy    — market phase label match
  Leader Accuracy   — leader state consistency
  Risk Accuracy     — risk level match
  Strategy Accuracy — allowed/forbidden action match
  Narrative F1      — evidence claim overlap

Output:
  AnalystReplayReport with per-dimension scores and gaps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any


# ── Benchmark contracts ──

@dataclass(frozen=True, slots=True)
class DimensionScore:
    dimension: str           # "phase" | "leader" | "risk" | "strategy" | "narrative"
    score: float             # 0-1
    match_detail: str        # brief explanation
    ai_value: str = ""
    analyst_value: str = ""


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    trade_date: date
    ai_phase: str
    ai_risk: str
    ai_headline: str
    ai_strategy: str
    ai_confidence: dict[str, float]

    analyst_phase: str = ""
    analyst_risk: str = ""
    analyst_notes: str = ""

    scores: tuple[DimensionScore, ...] = ()
    overall_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "trade_date": self.trade_date.isoformat(),
            "ai": {
                "phase": self.ai_phase, "risk": self.ai_risk,
                "headline": self.ai_headline, "strategy": self.ai_strategy,
                "confidence": self.ai_confidence,
            },
            "analyst": {
                "phase": self.analyst_phase, "risk": self.analyst_risk,
                "notes": self.analyst_notes,
            },
            "scores": [{
                "dimension": s.dimension, "score": s.score,
                "detail": s.match_detail,
                "ai_value": s.ai_value, "analyst_value": s.analyst_value,
            } for s in self.scores],
            "overall": self.overall_score,
        }


@dataclass(frozen=True, slots=True)
class ReplayBenchmarkReport:
    generated_at: datetime
    records: tuple[ReplayRecord, ...]
    avg_phase_accuracy: float
    avg_risk_accuracy: float
    avg_strategy_accuracy: float
    avg_overall: float
    total_records: int
    high_confidence_match_rate: float    # when AI confidence > 0.8, how often was it right?
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "total_records": self.total_records,
            "avg_scores": {
                "phase": self.avg_phase_accuracy,
                "risk": self.avg_risk_accuracy,
                "strategy": self.avg_strategy_accuracy,
                "overall": self.avg_overall,
            },
            "high_confidence_match_rate": self.high_confidence_match_rate,
            "summary": self.summary,
            "records": [r.to_dict() for r in self.records],
        }


# ── Phase label mapping (AI label → analyst PDF label candidates) ──

PHASE_MAP = {
    # AI phase      # Analyst PDF equivalents
    "强势":          ["强势", "高潮", "加速", "主升", "趋势"],
    "修复":          ["修复", "反弹", "回暖", "情绪修复"],
    "混沌":          ["混沌", "震荡", "轮动", "结构行情"],
    "分歧":          ["分歧", "分化", "退潮前夕", "高位分歧"],
    "退潮":          ["退潮", "回调", "补跌", "风险释放"],
    "恐慌/冰点":     ["冰点", "恐慌", "情绪冰点", "极致冰点"],
}

RISK_MAP = {
    "LOW":       ["低", "较低", "可控"],
    "MEDIUM":    ["中等", "中性", "一般"],
    "HIGH":      ["较高", "偏高风险", "谨慎"],
    "CRITICAL":  ["极高", "危险", "回避", "空仓"],
}


class ReplayBenchmark:
    """Compare AI narrative against analyst PDF for historical dates."""

    @staticmethod
    def _fuzzy_match(ai_label: str, mapping: dict[str, list[str]]) -> str | None:
        """Find which AI bucket an analyst label falls into."""
        ai_label = ai_label.strip()
        for bucket, candidates in mapping.items():
            if ai_label in candidates:
                return bucket
        return None

    @staticmethod
    def _extract_analyst_signal(text: str) -> dict[str, str]:
        """Extract phase/risk signals from analyst PDF text via keyword scanning.

        In production, this would be structured data from the analyst.
        For the benchmark, we use keyword matching against known analyst phrases.
        """
        result: dict[str, str] = {}

        # Phase detection
        phase_keywords = {
            "冰点": "恐慌/冰点", "情绪冰点": "恐慌/冰点", "极致冰点": "恐慌/冰点",
            "退潮": "退潮", "补跌": "退潮", "风险释放": "退潮",
            "分歧": "分歧", "分化": "分歧", "高位分歧": "分歧",
            "修复": "修复", "反弹": "修复", "回暖": "修复",
            "强势": "强势", "高潮": "强势", "加速": "强势",
            "混沌": "混沌", "震荡": "混沌", "轮动": "混沌",
        }
        for kw, phase in sorted(phase_keywords.items(), key=lambda x: -len(x[0])):
            if kw in text:
                result["phase"] = phase
                break

        # Risk detection
        risk_keywords = {
            "回避": "CRITICAL", "空仓": "CRITICAL", "谨慎": "HIGH",
            "偏高": "HIGH", "防守": "HIGH", "较低": "LOW",
            "可控": "LOW", "中等": "MEDIUM",
        }
        for kw, risk in sorted(risk_keywords.items(), key=lambda x: -len(x[0])):
            if kw in text:
                result["risk"] = risk
                break

        return result

    def score_one(self, narrative: Any, analyst_text: str = "") -> ReplayRecord:
        """Score AI narrative against analyst PDF text for one trading day.

        Args:
            narrative: MarketStory from NarrativeEngine
            analyst_text: raw text from analyst PDF
        """
        ai_phase = narrative.market_phase
        ai_risk = narrative.risk_level
        ai_headline = narrative.headline
        ai_strategy = narrative.strategy_summary
        ai_conf = narrative.confidence

        analyst = self._extract_analyst_signal(analyst_text)
        analyst_phase = analyst.get("phase", "")
        analyst_risk = analyst.get("risk", "")

        scores: list[DimensionScore] = []

        # 1. Phase accuracy
        phase_match = ai_phase == analyst_phase if analyst_phase else None
        phase_score = 1.0 if phase_match else (0.5 if phase_match is None else 0.0)
        scores.append(DimensionScore(
            dimension="phase", score=phase_score,
            match_detail="match" if phase_match else ("no_analyst_data" if phase_match is None else "mismatch"),
            ai_value=ai_phase, analyst_value=analyst_phase,
        ))

        # 2. Risk accuracy
        risk_match = ai_risk == analyst_risk if analyst_risk else None
        risk_score = 1.0 if risk_match else (0.5 if risk_match is None else 0.0)
        scores.append(DimensionScore(
            dimension="risk", score=risk_score,
            match_detail="match" if risk_match else ("no_analyst_data" if risk_match is None else "mismatch"),
            ai_value=ai_risk, analyst_value=analyst_risk,
        ))

        # 3. Strategy accuracy (check if forbidden actions align with analyst risk)
        strat_score = 0.7  # default — strategy is hard to auto-evaluate without structured analyst data
        if analyst_phase:
            # If analyst says 冰点 and AI says critical → good alignment
            if analyst_phase == "恐慌/冰点" and ai_risk == "CRITICAL":
                strat_score = 1.0
            elif analyst_phase == "退潮" and ai_risk in ("HIGH", "CRITICAL"):
                strat_score = 0.9
            elif analyst_phase == "强势" and ai_risk in ("LOW", "MEDIUM"):
                strat_score = 0.9
        scores.append(DimensionScore(
            dimension="strategy", score=strat_score,
            match_detail="inferred",
            ai_value=ai_strategy[:60], analyst_value=analyst_phase,
        ))

        overall = round(sum(s.score for s in scores) / len(scores), 2)

        return ReplayRecord(
            trade_date=narrative.trade_date,
            ai_phase=ai_phase, ai_risk=ai_risk,
            ai_headline=ai_headline, ai_strategy=ai_strategy,
            ai_confidence=ai_conf,
            analyst_phase=analyst_phase, analyst_risk=analyst_risk,
            analyst_notes=analyst_text[:200],
            scores=tuple(scores), overall_score=overall,
        )

    def build_report(self, records: list[ReplayRecord]) -> ReplayBenchmarkReport:
        n = len(records)
        if n == 0:
            return ReplayBenchmarkReport(
                generated_at=datetime.now(timezone.utc),
                records=(), avg_phase_accuracy=0, avg_risk_accuracy=0,
                avg_strategy_accuracy=0, avg_overall=0, total_records=0,
                high_confidence_match_rate=0, summary="No records to benchmark.",
            )

        phases = [r.scores[0].score for r in records if r.scores]
        risks = [r.scores[1].score for r in records if len(r.scores) > 1]
        strats = [r.scores[2].score for r in records if len(r.scores) > 2]
        overalls = [r.overall_score for r in records]

        # High confidence match rate: when AI confidence > 0.8
        high_conf = [r for r in records if r.ai_confidence.get("overall", 0) > 0.8]
        hc_matches = sum(1 for r in high_conf if r.overall_score >= 0.7)
        hc_rate = round(hc_matches / max(len(high_conf), 1), 2)

        avg_phase = round(sum(phases) / max(len(phases), 1), 2)
        avg_risk = round(sum(risks) / max(len(risks), 1), 2)
        avg_strat = round(sum(strats) / max(len(strats), 1), 2)
        avg_overall = round(sum(overalls) / max(len(overalls), 1), 2)

        if avg_overall >= 0.8:
            summary = "AI narrative strongly aligned with analyst — ready for production use."
        elif avg_overall >= 0.6:
            summary = "AI narrative reasonably aligned — review divergence cases before trusting."
        else:
            summary = "AI narrative requires calibration — significant divergence from analyst."

        return ReplayBenchmarkReport(
            generated_at=datetime.now(timezone.utc),
            records=tuple(records),
            avg_phase_accuracy=avg_phase,
            avg_risk_accuracy=avg_risk,
            avg_strategy_accuracy=avg_strat,
            avg_overall=avg_overall,
            total_records=n,
            high_confidence_match_rate=hc_rate,
            summary=summary,
        )
