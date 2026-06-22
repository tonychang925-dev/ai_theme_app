"""M4g: Recap Aggregation Service.

Aggregates ThemeStrength + LeaderScore into MarketRecapSnapshot
for read-only consumption by API and frontend.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.domain.services.theme_strength import ThemeStrength
from stock_processing_service.domain.services.leader_scoring import LeaderScore


RECAP_VERSION = "1.0.0"


@dataclass
class MarketRecap:
    version: str = RECAP_VERSION
    trade_date: str = ""
    top_themes: list[dict[str, Any]] = field(default_factory=list)
    market_summary: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    source_trace_id: str = ""


class RecapAggregationService:
    """Aggregates LeaderScores and ThemeStrengths into a MarketRecap."""

    def aggregate(
        self,
        trade_date: date,
        theme_strengths: list[ThemeStrength],
        leader_scores: list[LeaderScore],
        top_n: int = 8,
        evidence_items_count: int = 0,
    ) -> MarketRecap:
        td_str = trade_date.isoformat()
        diag: dict[str, Any] = {
            "input_theme_count": len(theme_strengths),
            "input_leader_count": len(leader_scores),
            "input_evidence_count": evidence_items_count,
            "degraded": False,
            "degraded_reasons": [],
        }

        top_themes = []
        for ts in theme_strengths[:top_n]:
            # Find top 3 leaders for this theme
            theme_leaders = [
                ls for ls in leader_scores
                if ls.theme_name == ts.theme_name
            ]
            theme_leaders.sort(key=lambda x: -x.leader_score)
            top3 = theme_leaders[:3]

            # Explain why this theme is strong
            reasons: list[str] = []
            if ts.stock_count >= 3:
                reasons.append(f"板块广度{ts.stock_count}只")
            if ts.resonance_count >= 2:
                reasons.append(f"多源共振({ts.resonance_count}源)")
            if ts.avg_leader_score >= 0.3:
                reasons.append("龙头强度高")
            if ts.avg_expectation_score >= 0.2:
                reasons.append("预期驱动强")
            # Check if research evidence is present and count it
            research_count = sum(
                1 for ls in leader_scores
                if ls.theme_name == ts.theme_name and "research" in ls.evidence_sources
            )
            if research_count:
                reasons.append(f"机构覆盖({research_count}篇)")
            if not reasons:
                reasons.append("事件驱动")

            # Get catalyst event from top leader's primary_reason
            catalyst = ""
            top_leader_reasons = [
                ls.primary_reason for ls in theme_leaders[:3]
                if ls.primary_reason
            ]
            if top_leader_reasons:
                catalyst = top_leader_reasons[0]

            top_themes.append({
                "rank": ts.rank,
                "theme_name": ts.theme_name,
                "strength_score": ts.strength_score,
                "stock_count": ts.stock_count,
                "leader_count": ts.leader_count,
                "avg_leader_score": ts.avg_leader_score,
                "resonance_count": ts.resonance_count,
                "why_strong": reasons,
                "catalyst": catalyst,
                "leaders": [
                    {
                        "stock_code": ls.stock_code,
                        "stock_name": ls.stock_name,
                        "leader_score": ls.leader_score,
                        "event_score": ls.event_score,
                        "expectation_score": ls.expectation_score,
                        "board_strength_score": ls.board_strength_score,
                        "evidence_sources": ls.evidence_sources,
                        "rank_in_theme": ls.rank_in_theme,
                    }
                    for ls in top3
                ],
                "evidence_sources": ts.evidence_sources,
            })

        all_leaders = [ls for ls in leader_scores if ls.leader_score > 0]
        all_sources: set[str] = set()
        for ls in all_leaders:
            all_sources.update(ls.evidence_sources)

        # Research diagnosis
        research_covered_stocks = len({
            ls.stock_code for ls in leader_scores
            if "research" in ls.evidence_sources
        })
        research_evidence_count = sum(
            1 for ls in leader_scores if "research" in ls.evidence_sources
        )

        market_summary = {
            "theme_count": len(theme_strengths),
            "leader_count": len(all_leaders),
            "evidence_source_count": len(all_sources),
            "evidence_sources": sorted(all_sources),
            "top_theme": top_themes[0]["theme_name"] if top_themes else "",
            "top_theme_strength": top_themes[0]["strength_score"] if top_themes else 0,
            "research_covered_stocks": research_covered_stocks,
            "research_evidence_count": research_evidence_count,
        }

        # Degradation check
        if not top_themes:
            diag["degraded"] = True
            diag["degraded_reasons"].append("no themes with leaders")

        return MarketRecap(
            version=RECAP_VERSION,
            trade_date=td_str,
            top_themes=top_themes,
            market_summary=market_summary,
            diagnostics=diag,
            source_trace_id=f"recap:{td_str}",
        )

    def to_snapshot_row(self, recap: MarketRecap) -> dict[str, Any]:
        """Convert MarketRecap to a DB row dict for market_recap_snapshot."""
        return {
            "trade_date": date.fromisoformat(recap.trade_date),
            "recap_json": {
                "version": recap.version,
                "trade_date": recap.trade_date,
                "top_themes": recap.top_themes,
                "market_summary": recap.market_summary,
                "diagnostics": recap.diagnostics,
            },
            "source_trace_id": recap.source_trace_id,
        }
