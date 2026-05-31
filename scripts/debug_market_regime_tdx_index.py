"""PR-11 debug tool: Market Regime analysis using real TDX index data.

Usage: PYTHONPATH=. python scripts/debug_market_regime_tdx_index.py
"""
import sys, json

sys.path.insert(0, ".")

from stock_processing_service.domain.services.market_regime.kline_technical_analyzer import KlineTechnicalAnalyzer
from stock_processing_service.domain.services.market_regime.broad_market_regime_engine import BroadMarketRegimeEngine
from stock_processing_service.domain.services.market_regime.short_term_sentiment_engine import ShortTermSentimentEngine
from stock_processing_service.domain.services.market_regime.market_regime_engine import MarketRegimeEngine

INDEX_CONFIG = {
    "000001": ("sh000001", "上证指数", "1"),
    "399001": ("sz399001", "深证成指", "0"),
    "399006": ("sz399006", "创业板指", "0"),
    "000300": ("sh000300", "沪深300", "1"),
    "000905": ("sh000905", "中证500", "1"),
    "000852": ("sh000852", "中证1000", "1"),
    "000688": ("sh000688", "科创50", "1"),
}


def run():
    import akshare as ak, pandas as pd

    for code, (symbol, name, market) in INDEX_CONFIG.items():
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is None or df.empty:
                print(f"{code} {name}: no data")
                continue
            bars = [{"close": float(r["close"]), "high": float(r["high"]),
                     "low": float(r["low"]), "volume": float(r.get("volume", 0)),
                     "amount": 0} for _, r in df.tail(120).iterrows()]

            r = KlineTechnicalAnalyzer().analyze(bars)
            t = r["trend"]
            m = r["ma"]
            mc = r["macd"]
            sr = r["support_resistance"]

            snap = {"up_count": 2000, "down_count": 3000, "limit_up_count": 35, "limit_down_count": 15}
            broad = BroadMarketRegimeEngine().build(index_kline=bars, market_snapshot=snap)

            print(f"\n{code} {name} ({len(bars)} bars)")
            print(f"  Close: {bars[-1]['close']:.1f}")
            print(f"  MA5={m['ma5']:.0f} MA10={m['ma10']:.0f} MA20={m['ma20']:.0f}")
            print(f"  MACD: DIF={mc['dif']:.1f} HIST={mc['hist']:.1f} state={mc['macd_state']}")
            print(f"  Support: {sr['nearest_support']:.0f}  Resist: {sr['nearest_resistance']:.0f}")
            print(f"  Trend: {t['trend_state']} score={t['trend_score']}")
            print(f"  Broad: {broad.broad_market_regime} score={broad.broad_market_score}")
        except Exception as e:
            print(f"{code} {name}: ERROR {e}")

    # Full regime
    print("\n=== Full Market Regime (上证指数) ===")
    df = ak.stock_zh_index_daily(symbol="sh000001")
    bars = [{"close": float(r["close"]), "high": float(r["high"]),
             "low": float(r["low"]), "volume": float(r.get("volume", 0)),
             "amount": 0} for _, r in df.tail(120).iterrows()]
    engine = MarketRegimeEngine()
    snap = {"up_count": 2000, "down_count": 3000, "limit_up_count": 35, "limit_down_count": 15}
    rr = engine.evaluate(trade_date=str(df["date"].iloc[-1])[:10], index_kline=bars,
                         market_snapshot=snap,
                         lifecycle_reviews=[{"lifecycle_state": "fermentation", "mainline_trade_alive": True}])
    d = rr.to_dict()
    keys = ["broad_market_regime", "short_term_sentiment", "mainline_environment",
            "market_structure", "allow_trade", "trade_mode", "position_limit",
            "allowed_actions", "forbidden_actions", "risk_notes"]
    for k in keys:
        print(f"  {k}: {d.get(k)}")


if __name__ == "__main__":
    run()
