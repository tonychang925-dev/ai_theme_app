"""Tests for PR-11: MarketRegimeEngine."""
import pytest
from stock_processing_service.domain.services.market_regime.kline_technical_analyzer import (
    KlineTechnicalAnalyzer,
)
from stock_processing_service.domain.services.market_regime.index_technical_analyzer import (
    IndexTechnicalAnalyzer,
)
from stock_processing_service.domain.services.market_regime.broad_market_regime_engine import (
    BroadMarketRegimeEngine,
)
from stock_processing_service.domain.services.market_regime.short_term_sentiment_engine import (
    ShortTermSentimentEngine,
)
from stock_processing_service.domain.services.market_regime.mainline_environment_engine import (
    MainlineEnvironmentEngine,
)
from stock_processing_service.domain.services.market_regime.trading_permission_engine import (
    TradingPermissionEngine,
)
from stock_processing_service.domain.services.market_regime.models import (
    BroadMarketRegimeReview, ShortTermSentimentReview, MainlineEnvironmentReview,
)
from stock_processing_service.domain.services.market_regime.market_regime_engine import (
    MarketRegimeEngine,
)


def _make_kline(n=60, base=3300, trend="flat"):
    """Generate kline bars. Oldest first (i=0), newest last (i=n-1)."""
    bars = []
    for i in range(n):
        if trend == "up":
            c = base + i * 3  # gradually rising from base
        elif trend == "down":
            c = base + 200 - i * 5  # starting high, dropping
        elif trend == "rebound":
            # weak rebound after big drop: high→crash→weak bounce
            if i < 30:
                c = base + 200 - i * 6  # drop from 3500 to 3320
            else:
                c = base + 20 + (i - 30) * 2  # weak bounce: 3320→3380, still below peak
        else:
            c = base
        bars.append({"close": c, "high": c + 20, "low": c - 20, "volume": 500 + (n - i) * 3, "amount": 5e7})
    return bars


class TestKlineTechnicalAnalyzer:

    def test_bullish_trend(self):
        r = KlineTechnicalAnalyzer().analyze(_make_kline(60, 3300, "up"))
        assert r["trend"]["trend_state"] == "bullish_trend"
        assert r["trend"]["trend_score"] >= 55

    def test_downtrend_rebound(self):
        bars = []
        for i in range(60):
            if i < 40: c, v = 3500 - i * 4, 1500
            else: c, v = 3344 + (i - 40) * 1.5, 400
            bars.append({"close": c, "high": c+20, "low": c-20, "volume": v, "amount": v*1000})
        r = KlineTechnicalAnalyzer().analyze(bars)
        # After sharp decline + weak bounce, trend should be conservative
        assert r["trend"]["trend_state"] in {"downtrend_rebound", "bearish_trend", "neutral_box", "weakening_trend"}

    def test_bearish_trend(self):
        r = KlineTechnicalAnalyzer().analyze(_make_kline(60, 3300, "down"))
        assert r["trend"]["trend_state"] in {"downtrend_rebound", "bearish_trend"}

    def test_insufficient_data(self):
        r = KlineTechnicalAnalyzer().analyze([{"close": 100, "high": 101, "low": 99, "volume": 100, "amount": 1e6}])
        assert r["trend"]["trend_state"] == "unknown"

    def test_ma_computation(self):
        r = KlineTechnicalAnalyzer().analyze(_make_kline(60, 3300, "flat"))
        assert r["ma"]["ma5"] is not None
        assert r["ma"]["ma20"] is not None


class TestIndexTechnicalAnalyzer:

    def test_output_structure(self):
        review = IndexTechnicalAnalyzer().analyze(index_code="000001.SH", kline_rows=_make_kline(60, 3300, "up"))
        assert review.trend_state != "unknown"
        assert review.index_code == "000001.SH"


class TestBroadMarketRegimeEngine:

    def test_downtrend_rebound(self):
        engine = BroadMarketRegimeEngine()
        result = engine.build(index_kline=_make_kline(60, 3300, "rebound"))
        assert result.broad_market_regime in {"downtrend_rebound", "bearish_adverse"}

    def test_crash_risk(self):
        engine = BroadMarketRegimeEngine()
        snap = {"up_count": 300, "down_count": 4700, "limit_up_count": 10, "limit_down_count": 80}
        result = engine.build(index_kline=_make_kline(60, 3100, "down"), market_snapshot=snap)
        assert result.broad_market_regime in {"downtrend_rebound", "bearish_adverse", "crash_risk"}

    def test_normal_market(self):
        engine = BroadMarketRegimeEngine()
        snap = {"up_count": 3000, "down_count": 2000, "limit_up_count": 55, "limit_down_count": 3}
        result = engine.build(index_kline=_make_kline(60, 3400, "up"), market_snapshot=snap)
        assert result.broad_market_regime in {"bullish_supportive", "neutral_choppy"}


class TestShortTermSentimentEngine:

    def test_attack(self):
        e = ShortTermSentimentEngine()
        r = e.build(market_snapshot={"limit_up_count": 70, "limit_down_count": 3, "up_count": 3500, "down_count": 1500})
        assert r.short_term_sentiment == "attack"

    def test_dead(self):
        e = ShortTermSentimentEngine()
        r = e.build(market_snapshot={"limit_up_count": 5, "limit_down_count": 50})
        assert r.short_term_sentiment == "dead"

    def test_retreat(self):
        e = ShortTermSentimentEngine()
        r = e.build(market_snapshot={"limit_up_count": 20, "limit_down_count": 18, "intraday_fade_status": "fade"})
        assert r.short_term_sentiment == "retreat"


class TestMainlineEnvironmentEngine:

    def test_no_mainline(self):
        e = MainlineEnvironmentEngine()
        r = e.build(lifecycle_reviews=[])
        assert r.mainline_environment == "no_confirmed_mainline"

    def test_tradable(self):
        e = MainlineEnvironmentEngine()
        r = e.build(lifecycle_reviews=[{"lifecycle_state": "fermentation", "mainline_trade_alive": True}])
        assert r.mainline_environment == "mainline_tradable"

    def test_fading(self):
        e = MainlineEnvironmentEngine()
        r = e.build(lifecycle_reviews=[{"lifecycle_state": "fade_confirmed", "mainline_trade_alive": False}])
        assert r.mainline_environment == "mainline_fading"


class TestTradingPermissionEngine:

    def test_no_mainline_no_trade(self):
        e = TradingPermissionEngine()
        broad = BroadMarketRegimeReview()
        sent = ShortTermSentimentReview()
        ml = MainlineEnvironmentReview()
        r = e.build(broad=broad, sentiment=sent, mainline=ml)
        assert r.allow_trade is False
        assert r.position_limit == 0.0

    def test_mainline_alive_downtrend_ultra_short(self):
        e = TradingPermissionEngine()
        broad = BroadMarketRegimeReview(broad_market_regime="downtrend_rebound")
        sent = ShortTermSentimentReview(short_term_sentiment="normal")
        ml = MainlineEnvironmentReview(mainline_environment="mainline_tradable", trade_alive_mainline_count=1, confirmed_mainline_count=1)
        r = e.build(broad=broad, sentiment=sent, mainline=ml)
        assert r.allow_trade is True
        assert r.trade_mode == "ultra_short_only"
        assert r.position_limit <= 0.2

    def test_mainline_active_bullish(self):
        e = TradingPermissionEngine()
        broad = BroadMarketRegimeReview(broad_market_regime="bullish_supportive")
        sent = ShortTermSentimentReview(short_term_sentiment="attack")
        ml = MainlineEnvironmentReview(mainline_environment="mainline_tradable", confirmed_mainline_count=2, trade_alive_mainline_count=2)
        r = e.build(broad=broad, sentiment=sent, mainline=ml)
        assert r.allow_trade is True
        assert r.trade_mode == "mainline_active"
        assert r.position_limit <= 0.5

    def test_fading_mainline_no_trade(self):
        e = TradingPermissionEngine()
        broad = BroadMarketRegimeReview(broad_market_regime="bullish_supportive")
        sent = ShortTermSentimentReview(short_term_sentiment="attack")
        ml = MainlineEnvironmentReview(mainline_environment="mainline_fading")
        r = e.build(broad=broad, sentiment=sent, mainline=ml)
        assert r.allow_trade is False

    def test_crash_risk_no_trade(self):
        e = TradingPermissionEngine()
        broad = BroadMarketRegimeReview(broad_market_regime="crash_risk")
        sent = ShortTermSentimentReview(short_term_sentiment="normal")
        ml = MainlineEnvironmentReview(mainline_environment="mainline_tradable", confirmed_mainline_count=1, trade_alive_mainline_count=1)
        r = e.build(broad=broad, sentiment=sent, mainline=ml)
        assert r.allow_trade is False

    def test_sentiment_dead_no_trade(self):
        e = TradingPermissionEngine()
        broad = BroadMarketRegimeReview(broad_market_regime="neutral_choppy")
        sent = ShortTermSentimentReview(short_term_sentiment="dead")
        ml = MainlineEnvironmentReview(mainline_environment="mainline_tradable", confirmed_mainline_count=1, trade_alive_mainline_count=1)
        r = e.build(broad=broad, sentiment=sent, mainline=ml)
        assert r.allow_trade is False


class TestMarketRegimeEngine:

    def test_empty_data_returns_conservative(self):
        e = MarketRegimeEngine()
        r = e.evaluate(trade_date="2026-04-29", index_kline=[], lifecycle_reviews=[])
        assert r.allow_trade is False
        assert r.mainline_environment == "no_confirmed_mainline"

    def test_output_structure(self):
        e = MarketRegimeEngine()
        r = e.evaluate(trade_date="2026-04-29",
                       index_kline=_make_kline(60, 3400, "up"),
                       market_snapshot={"up_count": 3000, "down_count": 2000, "limit_up_count": 60, "limit_down_count": 3},
                       lifecycle_reviews=[{"lifecycle_state": "fermentation", "mainline_trade_alive": True}])
        d = r.to_dict()
        assert "trade_date" in d
        assert "broad_market_regime" in d
        assert "allow_trade" in d
        assert "position_limit" in d
        assert d["allow_trade"] is True  # mainline + bullish + normal → active

    def test_does_not_modify_trading_principle(self):
        """CRITICAL: PR-11 must not output trading_principle."""
        e = MarketRegimeEngine()
        r = e.evaluate()
        d = r.to_dict()
        assert "trading_principle" not in d
        assert "watchlist" not in d
