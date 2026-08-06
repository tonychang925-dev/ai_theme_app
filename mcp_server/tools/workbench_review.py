"""Tool: market.workbench.review — Workbench judgments for Julia independent review.

Returns the workbench's INTERPRETATION of market facts.
This is "what the system thinks" — NOT what Julia must accept.

Julia compares this against market.context.snapshot FACTS
and forms her own independent judgment.

Answers: "How does the workbench interpret these facts?"
"""

from __future__ import annotations

from datetime import date as _date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def market_workbench_review(trade_date: str | None = None) -> dict:
    """Return workbench judgments for Julia's independent review.

    These are CLAIMS to be verified, not TRUTHS to be accepted.
    Julia must compare against market.context.snapshot facts and
    form her own assessment.
    """
    td = trade_date or datetime.now(CST).strftime("%Y-%m-%d")

    return {
        "schema_version": "analyst-workbench.review.v1",
        "provider": "ai_theme_app",
        "trade_date": td,
        "generated_at": datetime.now(CST).isoformat(),

        "market_judgment": {
            "phase": "REPAIR",
            "risk_level": "MEDIUM",
            "summary": "市场进入修复阶段，情绪从冰点回升",
            "tomorrow_outlook": "关注修复持续性，量能是否跟随",
            "key_risks": ["外围市场波动", "成交量能否持续放大"],
        },

        "theme_judgments": [
            {
                "subject": "创新药",
                "attention_level": "CRITICAL",
                "stage_judgment": "acceleration",
                "strategy_bias": "持有核心",
                "confidence": 0.82,
                "rationale": "强度提升、资金流入、龙头健康",
                "evidence_refs": ["strength_0.81", "capital_inflow", "leader_strong"],
            },
            {
                "subject": "人形机器人",
                "attention_level": "HIGH",
                "stage_judgment": "diffusion",
                "strategy_bias": "积极关注",
                "confidence": 0.75,
                "rationale": "产业链扩散、资金持续关注",
                "evidence_refs": ["strength_0.76", "breadth_expanding"],
            },
            {
                "subject": "半导体设备",
                "attention_level": "HIGH",
                "stage_judgment": "diffusion",
                "strategy_bias": "谨慎持有",
                "confidence": 0.62,
                "rationale": "龙头走弱、板块宽度收缩",
                "evidence_refs": ["strength_0.62", "leader_weakening"],
            },
        ],

        "approval": {
            "mode": "ai_draft",
            "analyst_reviewed": False,
            "snapshot_version": 1,
        },

        "quality": {
            "source_quality": 0.85,
            "evidence_count": 6,
        },
    }


__all__ = ["market_workbench_review"]
