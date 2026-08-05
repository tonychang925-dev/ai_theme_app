"""Tool 1: query_theme_status — Julia's "eyes on a theme"."""
from __future__ import annotations

from core.contracts.decision_envelope import ThemeStatusSnapshot, CausalLink, Lifecycle


def query_theme_status(theme_id: str) -> ThemeStatusSnapshot:
    """Return current lifecycle, heat, leaders, and causal context for one theme.

    Julia calls this when Tony asks: "最近机器人怎么样？"
    """
    # TODO Phase 2: Wire to actual data sources:
    #   theme_profile_ext, subject_rank_daily, subject_stock_map

    return ThemeStatusSnapshot(
        theme="机器人",
        lifecycle=Lifecycle.DIFFUSION,
        heat_score=87,
        leaders=("拓斯达", "绿的谐波"),
        money_flow="increase",
        causal_chain=(
            CausalLink(
                cause="政策催化 + 产业突破",
                effect="机器人产业链关注度提升",
                market_response="相关概念股走强",
                confidence=0.82,
            ),
        ),
        risk="medium",
    )
