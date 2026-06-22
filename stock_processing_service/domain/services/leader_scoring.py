"""M4e: Leader Scoring Engine V1 — rule-based.

Combines EvidenceFusionEngine output with board strength signals
to produce per-stock-per-theme leader scores.

Design doc §M4e: Leader Scoring Engine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.domain.services.evidence_fusion import (
    EvidenceItem,
    EvidenceFusionEngine,
)

# ── Scoring weights ─────────────────────────────────────────────

W_EVENT = 0.40         # Event-driven evidence (THS + CNInfo + Eastmoney + JYHF)
W_EXPECTATION = 0.25   # EPS expectation
W_RESONANCE = 0.20     # Multi-source resonance bonus
W_BOARD = 0.15         # Board/trading strength


# ── Board strength scoring ──────────────────────────────────────


def compute_board_strength(
    *,
    is_limit_up: bool = False,
    consecutive_boards: int = 0,
    pct_chg: float = 0.0,
    amount_rank_pct: float | None = None,
    turnover_rank_pct: float | None = None,
) -> float:
    """Compute board (trading) strength score 0.0-1.0.

    Args:
        is_limit_up: whether the stock hit limit-up
        consecutive_boards: number of consecutive limit-up days
        pct_chg: daily percentage change
        amount_rank_pct: amount percentile within theme (0-100, lower=top)
        turnover_rank_pct: turnover percentile within theme (0-100, lower=top)
    """
    score = 0.0

    # Limit-up scoring
    if is_limit_up:
        score += 0.40
        if consecutive_boards >= 3:
            score += 0.30  # 连板龙头
        elif consecutive_boards >= 2:
            score += 0.20  # 2连板
    elif pct_chg >= 9.5:
        score += 0.35  # 接近涨停
    elif pct_chg >= 5.0:
        score += 0.20  # 大涨
    elif pct_chg >= 2.0:
        score += 0.10  # 小涨
    elif pct_chg > 0:
        score += 0.05  # 微涨

    # Volume/turnover signals
    if amount_rank_pct is not None and amount_rank_pct <= 20:
        score += 0.10  # top 20% by amount
    if turnover_rank_pct is not None and turnover_rank_pct <= 20:
        score += 0.10  # top 20% by turnover

    return min(score, 1.0)


# ── LeaderScore ─────────────────────────────────────────────────


@dataclass(frozen=True)
class LeaderScore:
    """Per-stock-per-theme leader score."""

    trade_date: date
    stock_code: str
    stock_name: str
    theme_name: str
    leader_score: float          # 0.0 — 1.0 composite
    event_score: float           # from evidence fusion
    expectation_score: float     # from EPS
    resonance_score: float       # multi-source resonance bonus
    board_strength_score: float  # trading strength
    rank_in_theme: int = 0
    evidence_sources: list[str] = field(default_factory=list)
    source_trace_id: str = ""
    confidence: float = 0.0


# ── Leader Scoring Engine ───────────────────────────────────────


class LeaderScoringEngine:
    """Rule-based leader scoring using fused evidence + board signals."""

    def __init__(
        self,
        fusion_engine: EvidenceFusionEngine | None = None,
    ) -> None:
        self._fusion = fusion_engine or EvidenceFusionEngine()

    def score(
        self,
        trade_date: date,
        evidence_items: list[EvidenceItem],
        board_signals: dict[str, dict[str, Any]] | None = None,
    ) -> list[LeaderScore]:
        """Compute leader scores for a set of stocks.

        Args:
            trade_date: scoring date
            evidence_items: all evidence items (across stocks/themes)
            board_signals: {stock_code: {is_limit_up, consecutive_boards, ...}}
        """
        signals = board_signals or {}

        # Step 1: Fuse evidence
        fused_list = self._fusion.fuse(trade_date, evidence_items)

        # Step 2: Score each stock-theme pair
        scores: list[LeaderScore] = []
        for fused in fused_list:
            bs = signals.get(fused.stock_code, {})
            board = compute_board_strength(
                is_limit_up=bs.get("is_limit_up", False),
                consecutive_boards=bs.get("consecutive_boards", 0),
                pct_chg=bs.get("pct_chg", 0.0),
                amount_rank_pct=bs.get("amount_rank_pct"),
                turnover_rank_pct=bs.get("turnover_rank_pct"),
            )

            # Resonance: bonus from multi-source agreement
            resonance_bonus = 0.0
            if fused.is_resonance:
                if fused.source_count >= 4:
                    resonance_bonus = 0.85
                elif fused.source_count >= 3:
                    resonance_bonus = 0.70
                elif fused.source_count >= 2:
                    resonance_bonus = 0.50

            # Composite score
            leader = (
                normalize(fused.event_score) * W_EVENT
                + normalize(fused.expectation_score) * W_EXPECTATION
                + resonance_bonus * W_RESONANCE
                + board * W_BOARD
            )
            leader = round(min(leader, 1.0), 4)

            scores.append(LeaderScore(
                trade_date=trade_date,
                stock_code=fused.stock_code,
                stock_name=fused.stock_name,
                theme_name=fused.theme_name,
                leader_score=leader,
                event_score=round(fused.event_score, 4),
                expectation_score=round(fused.expectation_score, 4),
                resonance_score=round(resonance_bonus, 4),
                board_strength_score=round(board, 4),
                evidence_sources=fused.evidence_sources,
                source_trace_id=f"leader:{trade_date.isoformat()}:{fused.stock_code}:{fused.theme_name}",
                confidence=round(fused.confidence, 2),
            ))

        # Step 3: Rank within each theme
        by_theme: dict[str, list[LeaderScore]] = {}
        for s in scores:
            by_theme.setdefault(s.theme_name, []).append(s)

        ranked: list[LeaderScore] = []
        for theme, theme_scores in by_theme.items():
            sorted_scores = sorted(theme_scores, key=lambda x: -x.leader_score)
            for rank, s in enumerate(sorted_scores, 1):
                ranked.append(LeaderScore(
                    trade_date=s.trade_date,
                    stock_code=s.stock_code,
                    stock_name=s.stock_name,
                    theme_name=s.theme_name,
                    leader_score=s.leader_score,
                    event_score=s.event_score,
                    expectation_score=s.expectation_score,
                    resonance_score=s.resonance_score,
                    board_strength_score=s.board_strength_score,
                    rank_in_theme=rank,
                    evidence_sources=s.evidence_sources,
                    source_trace_id=s.source_trace_id,
                    confidence=s.confidence,
                ))

        return sorted(ranked, key=lambda x: (x.theme_name, x.rank_in_theme))


def normalize(value: float, cap: float = 1.0) -> float:
    """Normalize a score to 0.0-1.0 range."""
    return max(0.0, min(float(value) / (cap if cap > 0 else 1.0), 1.0))
