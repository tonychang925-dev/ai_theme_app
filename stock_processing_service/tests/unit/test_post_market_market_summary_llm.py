from __future__ import annotations

from datetime import date

from stock_processing_service.application.services.post_market_market_summary_llm import (
    PostMarketMarketSummaryLlmService,
)


class _FakeParser:
    async def parse_content(self, content: str):
        assert "输入JSON" in content
        return {
            "market_overview": "指数震荡修复，量能小幅收缩，短线情绪偏强",
            "top_gain_concepts": ["培育钻石 +6.62%", "超级电容 +4.68%", "PET铜箔 +4.52%"],
            "index_performance": ["深证成指 +0.80%", "创业板指 +1.96%"],
            "mainstream_focus": ["培育钻石", "MLCC/电容", "光通信"],
            "activity_context": "培育钻石低开后走高，超级电容高开高走，权重方向相对低迷。",
            "board_efficiency": "较好",
            "risk_notes": ["量能收缩", "权重拖累"],
            "action_bias": "精选弱转强",
            "confidence": 0.86,
        }


def test_market_summary_llm_normalizes_structured_response(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-real-for-unit-test")
    service = PostMarketMarketSummaryLlmService(parser_factory=lambda: _FakeParser())

    import asyncio

    result = asyncio.run(
        service.build(
            trade_date=date(2026, 5, 28),
            report_context={
                "market": {
                    "market_bias": "修复",
                    "up_count": 2708,
                    "down_count": 2296,
                    "limit_up_count": 145,
                    "limit_down_count": 14,
                },
                "theme_capital_flow": [{"resolved_theme_name": "培育钻石"}],
                "stock_facts": [{"stock_name": "惠丰钻石", "pct_chg": 30, "limit_up": True}],
            },
        )
    )

    assert result is not None
    assert result["source"] == "llm"
    assert result["mainstream_focus"] == ["培育钻石", "MLCC/电容", "光通信"]
    assert result["board_efficiency"] == "较好"
    assert result["confidence"] == 0.86


def test_market_summary_llm_rejects_incomplete_response() -> None:
    assert PostMarketMarketSummaryLlmService.normalize_response({"market_overview": "ok"}) is None
