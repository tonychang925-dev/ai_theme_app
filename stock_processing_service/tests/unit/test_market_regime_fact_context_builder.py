from __future__ import annotations

from stock_processing_service.application.services.market_regime.market_regime_fact_context_builder import (
    MarketRegimeFactContextBuilder,
)


def test_enrich_index_technical_review_computes_support_resistance_and_hint() -> None:
    row = {
        "index_code": "000001",
        "index_name": "上证指数",
        "trend_state": "bearish_trend",
        "trend_score": 30,
        "above_ma5": False,
        "above_ma10": False,
        "above_ma20": False,
        "above_ma60": True,
        "ma5": 4111.77,
        "ma10": 4121.23,
        "ma20": 4147.38,
        "ma60": 4061.92,
        "support_level": 4055.83,
        "resistance_level": 4258.86,
        "macd_state": "above_zero_weakening",
        "volume_pattern": "normal",
        "risk_flags_json": ["跌破MA5", "跌破MA20", "空头趋势"],
    }

    enriched = MarketRegimeFactContextBuilder._enrich_index_technical_review(
        row,
        {"000001": 4068.569},
    )

    assert enriched["close"] == 4068.569
    assert enriched["nearest_support_level"] == 4055.83
    assert enriched["nearest_resistance_level"] == 4258.86
    assert enriched["support_distance_pct"] == 0.31
    assert enriched["resistance_distance_pct"] == 4.68
    assert enriched["support_status"] == "near_support"
    assert enriched["resistance_status"] == "resistance_available"
    assert enriched["warning_level"] == "watch"
    assert "接近支撑位" in enriched["index_trade_hint"]
