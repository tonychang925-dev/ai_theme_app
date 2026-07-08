"""M2.5 Phase 3.3 — Market Memory Engine.

"What have I seen before that looks like today?"

Instead of adding more metrics, retrieves similar historical market states
and analyzes what happened next. This is what makes an experienced analyst:
pattern recognition from memory, not daily recalculation.

Core capability:
  1. MarketFingerprint — compact state vector for fast comparison
  2. Similarity search — top-N historical matches by fingerprint distance
  3. Transition analysis — given similar past states, what happened next?
  4. Narrative enrichment — "historically, this pattern led to X 60% of the time"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from .contracts import MarketMetricsSnapshot


# ── Market Fingerprint ──

@dataclass(frozen=True, slots=True)
class MarketFingerprint:
    """Compact state signature for fast historical comparison.

    Each dimension is bucketed to 2-5 levels for robust matching.
    """
    trade_date: date

    # Phase (10 levels → 5 buckets)
    phase_bucket: int  # 0=启动/修复, 1=发酵/加速, 2=高潮, 3=分歧/派发, 4=恐慌/冰点

    # Death (0-3)
    death_bucket: int  # 0=SAFE, 1=WARNING, 2=DANGER, 3=CRITICAL

    # Relay feedback (-100~100 → 5 buckets)
    feedback_bucket: int  # -2=强负, -1=负, 0=中性, 1=正, 2=强正

    # Limit-up count (→ 5 buckets)
    limitup_bucket: int  # 0=极低(<20), 1=低(20-40), 2=正常(40-80), 3=高(80-150), 4=极高(>150)

    # Sealed ratio (→ 3 buckets)
    sealed_bucket: int  # 0=低(<0.5), 1=中(0.5-0.8), 2=高(>0.8)

    # Leader health (→ 4 buckets)
    leader_bucket: int  # 0=COLLAPSE, 1=WEAK, 2=NORMAL, 3=STRONG

    # Raw values for display
    raw_values: dict[str, Any] = field(default_factory=dict)

    def distance(self, other: MarketFingerprint) -> int:
        """Hamming-like distance: sum of absolute bucket differences."""
        return (
            abs(self.phase_bucket - other.phase_bucket) * 3   # phase is most important
            + abs(self.death_bucket - other.death_bucket) * 3
            + abs(self.feedback_bucket - other.feedback_bucket) * 2
            + abs(self.limitup_bucket - other.limitup_bucket)
            + abs(self.sealed_bucket - other.sealed_bucket)
            + abs(self.leader_bucket - other.leader_bucket) * 2
        )

    @staticmethod
    def from_snapshot(snap: MarketMetricsSnapshot) -> MarketFingerprint:
        b = snap.breadth
        l = snap.limitup
        r = snap.relay
        leader = snap.leader_evolution
        death = snap.high_position_death

        # Phase bucket (requires DiagnosisEngine output — approximate from relay+death)
        fb = r.feedback_score
        if death and death.death_label == "CRITICAL":
            phase_b = 4  # 恐慌/冰点
        elif fb < -30:
            phase_b = 3  # 分歧/派发/退潮
        elif fb > 40:
            phase_b = 2  # 高潮
        elif fb > 10:
            phase_b = 1  # 发酵/加速
        else:
            phase_b = 0  # 混沌/启动/修复

        # Death bucket
        if death and death.death_label == "CRITICAL":   db = 3
        elif death and death.death_label == "DANGER":    db = 2
        elif death and death.death_label == "WARNING":   db = 1
        else:                                             db = 0

        # Feedback bucket
        if fb >= 60:       fbb = 2
        elif fb >= 20:     fbb = 1
        elif fb >= -20:    fbb = 0
        elif fb >= -60:    fbb = -1
        else:              fbb = -2

        # Limit-up bucket
        lu = l.total_count
        if lu > 150:      lub = 4
        elif lu > 80:     lub = 3
        elif lu > 40:     lub = 2
        elif lu > 20:     lub = 1
        else:             lub = 0

        # Sealed bucket
        sr = l.sealed_board_ratio
        if sr > 0.8:      sb = 2
        elif sr > 0.5:    sb = 1
        else:             sb = 0

        # Leader bucket
        if leader:
            lh = leader.leader_health_label
            if lh == "STRONG":       lb = 3
            elif lh == "NORMAL":     lb = 2
            elif lh == "WEAK":       lb = 1
            else:                    lb = 0
        else:
            lb = 1

        return MarketFingerprint(
            trade_date=snap.trade_date,
            phase_bucket=phase_b, death_bucket=db,
            feedback_bucket=fbb, limitup_bucket=lub,
            sealed_bucket=sb, leader_bucket=lb,
            raw_values={
                "phase": phase_b, "death_label": death.death_label if death else "N/A",
                "feedback": fb, "limitup": lu, "sealed": sr,
                "leader_health": leader.leader_health_label if leader else "N/A",
            },
        )


# ── Memory types ──

@dataclass(frozen=True, slots=True)
class SimilarDay:
    """A historical day that resembles the current market state."""
    trade_date: date
    fingerprint: MarketFingerprint
    distance: int              # lower = more similar
    similarity_pct: float      # 0-100, normalized

    # What happened next (next trading day)
    next_day_phase: str = ""           # next day's approximated phase
    next_day_feedback: float = 0.0     # next day's feedback score
    transition_label: str = ""         # "修复" | "持续退潮" | "震荡" | "反转"


@dataclass(frozen=True, slots=True)
class TransitionAnalysis:
    """What happened after similar historical states?"""
    query_date: date
    similar_days: tuple[SimilarDay, ...]
    total_similar: int

    # Transition probabilities
    improved_pct: float       # % of similar days that improved (feedback_score increased)
    worsened_pct: float       # % that worsened
    stable_pct: float         # % that stayed similar

    # Expected next state
    expected_next_phase: str
    avg_next_feedback: float

    # Narrative
    memory_summary: str       # "历史上类似状态12次，其中7次(58%)在次日出现修复"
    best_match_date: date | None
    best_match_narrative: str = ""


# ── Memory Engine ──

class MarketMemoryEngine:
    """Retrieve similar historical states and analyze transitions."""

    def __init__(self):
        self._memory: dict[date, MarketFingerprint] = {}

    def remember(self, fingerprint: MarketFingerprint) -> None:
        """Store a market state in memory."""
        self._memory[fingerprint.trade_date] = fingerprint

    def remember_batch(self, fingerprints: list[MarketFingerprint]) -> None:
        for fp in fingerprints:
            self._memory[fp.trade_date] = fp

    def find_similar(self, query: MarketFingerprint,
                     top_n: int = 5,
                     min_distance: int = 0,
                     exclude_same_date: bool = True) -> list[SimilarDay]:
        """Find top-N most similar historical states.

        Args:
            query: current day's fingerprint
            top_n: number of matches
            min_distance: minimum distance (0 = all matches)
            exclude_same_date: skip the query date itself
        """
        candidates: list[tuple[date, int]] = []
        for dt, fp in self._memory.items():
            if exclude_same_date and dt == query.trade_date:
                continue
            d = query.distance(fp)
            if d >= min_distance:
                candidates.append((dt, d))

        candidates.sort(key=lambda x: x[1])

        if not candidates:
            return []

        # Normalize to similarity %
        max_d = max(12, candidates[0][1] + 1)  # avoid div by zero
        results: list[SimilarDay] = []
        for dt, dist in candidates[:top_n]:
            sim_pct = round(max(0, (1 - dist / max_d)) * 100, 1)
            fp = self._memory[dt]

            # Find next day's state (if in memory)
            next_day = dt + timedelta(days=1)
            next_fp = self._memory.get(next_day)
            if next_fp:
                next_phase = self._phase_name(next_fp.phase_bucket)
                next_fb = next_fp.raw_values.get("feedback", 0)
                if next_fp.phase_bucket < fp.phase_bucket:
                    t_label = "修复"
                elif next_fp.phase_bucket > fp.phase_bucket:
                    t_label = "持续退潮"
                else:
                    t_label = "震荡"
            else:
                next_phase = "未知"
                next_fb = 0
                t_label = "未知"

            results.append(SimilarDay(
                trade_date=dt, fingerprint=fp, distance=dist,
                similarity_pct=sim_pct,
                next_day_phase=next_phase, next_day_feedback=next_fb,
                transition_label=t_label,
            ))

        return results

    def analyze_transition(self, query: MarketFingerprint,
                           top_n: int = 5) -> TransitionAnalysis:
        """Analyze what happened after similar historical states."""
        similar = self.find_similar(query, top_n=top_n)
        total = len(similar)

        if total == 0:
            return TransitionAnalysis(
                query_date=query.trade_date,
                similar_days=(), total_similar=0,
                improved_pct=0, worsened_pct=0, stable_pct=0,
                expected_next_phase="未知", avg_next_feedback=0,
                memory_summary="无足够历史数据进行比较。",
                best_match_date=None,
            )

        improved = sum(1 for s in similar if s.transition_label == "修复")
        worsened = sum(1 for s in similar if s.transition_label == "持续退潮")
        stable = total - improved - worsened
        avg_fb = round(sum(s.next_day_feedback for s in similar) / total, 1)

        # Expected next phase: most common transition
        from collections import Counter
        phases = Counter(s.next_day_phase for s in similar if s.next_day_phase != "未知")
        expected = phases.most_common(1)[0][0] if phases else "未知"

        best = similar[0] if similar else None
        improved_pct = round(improved / total * 100, 1)

        if improved_pct >= 60:
            summary = f"历史上类似状态{total}次，其中{improved}次({improved_pct}%)在次日出现修复，预期向好。"
        elif worsened >= total * 0.5:
            summary = f"历史上类似状态{total}次，其中{worsened}次在次日持续退潮，应保持防守。"
        else:
            summary = f"历史上类似状态{total}次，走势分化({improved}修复/{worsened}恶化/{stable}震荡)，方向不明。"

        return TransitionAnalysis(
            query_date=query.trade_date,
            similar_days=tuple(similar),
            total_similar=total,
            improved_pct=round(improved / total * 100, 1),
            worsened_pct=round(worsened / total * 100, 1),
            stable_pct=round(stable / total * 100, 1),
            expected_next_phase=expected,
            avg_next_feedback=avg_fb,
            memory_summary=summary,
            best_match_date=best.trade_date if best else None,
            best_match_narrative=f"最相似: {best.trade_date.isoformat()}({best.similarity_pct:.0f}%相似), "
                                 f"次日: {best.transition_label}" if best else "",
        )

    @staticmethod
    def _phase_name(bucket: int) -> str:
        return {0: "混沌/修复", 1: "发酵/加速", 2: "高潮", 3: "分歧/退潮", 4: "恐慌/冰点"}.get(bucket, "未知")
