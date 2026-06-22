"""M4f: Theme Strength Engine — aggregates LeaderScores into per-theme rankings.

Design doc §M4f: Theme Strength Engine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.domain.services.leader_scoring import LeaderScore

# ── Weights ──────────────────────────────────────────────────────

W_LIMIT_UP = 0.30
W_LEADER_AVG = 0.25
W_RESONANCE = 0.20
W_EXPECTATION = 0.15
W_BREADTH = 0.10


# ── ThemeStrength ────────────────────────────────────────────────


@dataclass(frozen=True)
class ThemeStrength:
    trade_date: date
    theme_name: str
    strength_score: float
    rank: int = 0
    stock_count: int = 0
    limit_up_count: int = 0
    leader_count: int = 0
    avg_leader_score: float = 0.0
    top_leader_score: float = 0.0
    avg_event_score: float = 0.0
    avg_expectation_score: float = 0.0
    resonance_count: int = 0
    top_stocks: list[dict[str, Any]] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)
    source_trace_id: str = ""


# ── Engine ───────────────────────────────────────────────────────


class ThemeStrengthEngine:
    """Aggregate LeaderScores into per-theme strength rankings."""

    def compute(
        self,
        trade_date: date,
        leader_scores: list[LeaderScore],
    ) -> list[ThemeStrength]:
        if not leader_scores:
            return []

        # Group by theme
        by_theme: dict[str, list[LeaderScore]] = {}
        for ls in leader_scores:
            by_theme.setdefault(ls.theme_name, []).append(ls)

        strengths: list[ThemeStrength] = []
        for theme, scores in by_theme.items():
            n = len(scores)
            leader_scores_list = [s.leader_score for s in scores]
            event_scores = [s.event_score for s in scores]
            expectation_scores = [s.expectation_score for s in scores]
            resonance_count = sum(1 for s in scores if s.resonance_score > 0)
            limit_up_estimate = min(n, max(1, int(n * 0.6)))

            avg_leader = sum(leader_scores_list) / n
            top_leader = max(leader_scores_list)
            avg_event = sum(event_scores) / n if event_scores else 0.0
            avg_expectation = sum(expectation_scores) / n if expectation_scores else 0.0

            # Breadth: logarithmic scale to reward larger themes without
            # over-rewarding massive ones
            breadth = min(1.0, (n ** 0.5) / 8)

            # Limit-up score: normalized by max reasonable count
            limit_up_score = min(1.0, limit_up_estimate / 15)

            # Resonance: fraction of leaders with 2+ sources
            resonance_ratio = resonance_count / n if n > 0 else 0.0

            strength = (
                limit_up_score * W_LIMIT_UP
                + avg_leader * W_LEADER_AVG
                + resonance_ratio * W_RESONANCE
                + avg_expectation * W_EXPECTATION
                + breadth * W_BREADTH
            )
            strength = round(min(strength, 1.0), 4)

            # Top stocks (by leader_score descending)
            sorted_scores = sorted(scores, key=lambda x: -x.leader_score)[:5]
            top_stocks = [
                {
                    "stock_code": s.stock_code,
                    "stock_name": s.stock_name,
                    "leader_score": s.leader_score,
                    "rank_in_theme": s.rank_in_theme,
                }
                for s in sorted_scores
            ]

            # Union of all evidence sources across leaders
            all_sources: set[str] = set()
            for s in scores:
                all_sources.update(s.evidence_sources)

            strengths.append(ThemeStrength(
                trade_date=trade_date,
                theme_name=theme,
                strength_score=strength,
                stock_count=n,
                limit_up_count=limit_up_estimate,
                leader_count=resonance_count,
                avg_leader_score=round(avg_leader, 4),
                top_leader_score=round(top_leader, 4),
                avg_event_score=round(avg_event, 4),
                avg_expectation_score=round(avg_expectation, 4),
                resonance_count=resonance_count,
                top_stocks=top_stocks,
                evidence_sources=sorted(all_sources),
                source_trace_id=f"theme_strength:{trade_date.isoformat()}:{theme}",
            ))

        # Rank by strength descending
        strengths.sort(key=lambda x: -x.strength_score)
        ranked: list[ThemeStrength] = []
        for rank, s in enumerate(strengths, 1):
            ranked.append(ThemeStrength(
                trade_date=s.trade_date,
                theme_name=s.theme_name,
                strength_score=s.strength_score,
                rank=rank,
                stock_count=s.stock_count,
                limit_up_count=s.limit_up_count,
                leader_count=s.leader_count,
                avg_leader_score=s.avg_leader_score,
                top_leader_score=s.top_leader_score,
                avg_event_score=s.avg_event_score,
                avg_expectation_score=s.avg_expectation_score,
                resonance_count=s.resonance_count,
                top_stocks=s.top_stocks,
                evidence_sources=s.evidence_sources,
                source_trace_id=s.source_trace_id,
            ))

        return ranked
