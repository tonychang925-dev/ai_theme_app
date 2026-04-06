from __future__ import annotations

from stock_service.models import MarketEnvironmentJudgement, MarketEnvironmentMetrics


def _clip(value: float, upper: float = 100.0) -> float:
    return max(0.0, min(upper, round(value, 2)))


def _as_float(value: float) -> float:
    return float(value or 0.0)


class MarketEnvironmentJudgementService:
    """
    P3.phase3 环境层：
    先回答“今天整个市场适不适合进攻”，再让题材/个股判断承接这个结论。
    当前版本只使用日频可稳定获得的事实指标，因此明确标记为 daily_proxy。
    """

    def compute_breadth_score(self, metrics: MarketEnvironmentMetrics) -> float:
        ratio = _as_float(metrics.advance_decline_ratio)
        if ratio >= 1.8:
            return 90.0
        if ratio >= 1.35:
            return 75.0
        if ratio >= 1.0:
            return 60.0
        if ratio >= 0.8:
            return 45.0
        return 25.0

    def compute_short_term_sentiment_score(self, metrics: MarketEnvironmentMetrics) -> float:
        ratio = _as_float(metrics.limit_up_down_ratio)
        if int(metrics.limit_up_count) >= 50 and ratio >= 4.0:
            return 92.0
        if int(metrics.limit_up_count) >= 25 and ratio >= 2.5:
            return 78.0
        if int(metrics.limit_up_count) >= 12 and ratio >= 1.4:
            return 62.0
        if int(metrics.limit_up_count) >= 6 and ratio >= 1.0:
            return 48.0
        return 25.0

    def compute_relay_sentiment_score(self, metrics: MarketEnvironmentMetrics) -> float:
        open_red = _as_float(metrics.yesterday_limit_up_open_red_ratio) * 100.0
        premium = _as_float(metrics.yesterday_limit_up_premium_ratio) * 100.0
        fail = _as_float(metrics.yesterday_limit_up_fail_ratio) * 100.0
        score = open_red * 0.35 + premium * 0.45 + min(int(metrics.high_mark_strong_count), 10) * 2.5
        score -= fail * 0.35
        score -= min(int(metrics.high_mark_weak_count), 10) * 2.0
        return _clip(score)

    def compute_intraday_fade_score(self, metrics: MarketEnvironmentMetrics) -> float:
        penalty = _as_float(metrics.morning_high_then_fall_ratio) * 100.0 * 0.55
        penalty += _as_float(metrics.intraday_fade_ratio) * 100.0 * 0.45
        return _clip(100.0 - penalty)

    def compute_liquidity_score(self, metrics: MarketEnvironmentMetrics) -> float:
        amount_delta = _as_float(metrics.market_volume_change_pct)
        close_proxy = _as_float(metrics.market_avg_close_pct)
        score = 50.0
        if amount_delta >= 8.0:
            score += 25.0
        elif amount_delta >= 2.0:
            score += 15.0
        elif amount_delta <= -8.0:
            score -= 20.0
        elif amount_delta <= -2.0:
            score -= 10.0

        if close_proxy >= 1.0:
            score += 15.0
        elif close_proxy >= 0.3:
            score += 8.0
        elif close_proxy <= -1.0:
            score -= 15.0
        elif close_proxy <= -0.3:
            score -= 8.0
        return _clip(score)

    def compute_market_health_score(self, metrics: MarketEnvironmentMetrics) -> float:
        breadth = self.compute_breadth_score(metrics)
        short_term = self.compute_short_term_sentiment_score(metrics)
        relay = self.compute_relay_sentiment_score(metrics)
        fade = self.compute_intraday_fade_score(metrics)
        liquidity = self.compute_liquidity_score(metrics)
        score = (
            breadth * 0.20
            + short_term * 0.25
            + relay * 0.25
            + fade * 0.15
            + liquidity * 0.15
        )
        return _clip(score)

    def classify_breadth_status(self, metrics: MarketEnvironmentMetrics) -> str:
        ratio = _as_float(metrics.advance_decline_ratio)
        if ratio >= 1.5:
            return "市场广度强"
        if ratio >= 1.0:
            return "市场广度中性"
        return "市场广度偏弱"

    def classify_short_term_sentiment_status(self, metrics: MarketEnvironmentMetrics) -> str:
        if int(metrics.limit_up_count) >= 30 and _as_float(metrics.limit_up_down_ratio) >= 2.5:
            return "短线情绪活跃"
        if int(metrics.limit_up_count) >= 12 and _as_float(metrics.limit_up_down_ratio) >= 1.2:
            return "短线情绪一般"
        return "短线情绪走弱"

    def classify_relay_sentiment_status(self, metrics: MarketEnvironmentMetrics) -> str:
        if (
            _as_float(metrics.yesterday_limit_up_open_red_ratio) >= 0.6
            and _as_float(metrics.yesterday_limit_up_premium_ratio) >= 0.55
            and _as_float(metrics.yesterday_limit_up_fail_ratio) <= 0.25
        ):
            return "接力生态健康"
        if (
            _as_float(metrics.yesterday_limit_up_open_red_ratio) >= 0.4
            and _as_float(metrics.yesterday_limit_up_fail_ratio) <= 0.4
        ):
            return "接力生态分化"
        return "接力生态偏弱"

    def classify_intraday_fade_status(self, metrics: MarketEnvironmentMetrics) -> str:
        if _as_float(metrics.morning_high_then_fall_ratio) >= 0.22 or _as_float(metrics.intraday_fade_ratio) >= 0.18:
            return "冲高回落风险高"
        if _as_float(metrics.morning_high_then_fall_ratio) >= 0.12 or _as_float(metrics.intraday_fade_ratio) >= 0.10:
            return "冲高回落风险中等"
        return "冲高回落风险可控"

    def classify_market_bias(self, health_score: float) -> tuple[str, str]:
        if health_score >= 75.0:
            return "risk_on", "主做"
        if health_score >= 60.0:
            return "neutral", "谨慎试错"
        if health_score >= 45.0:
            return "risk_off", "防守"
        return "risk_off", "放弃"

    def build_conclusion(self, action_bias: str, relay_status: str, fade_status: str) -> str:
        if action_bias == "主做":
            return "大环境提供保护，可围绕主线前排与高辨识度个股积极进攻"
        if action_bias == "谨慎试错":
            return f"环境仍可试错，但需控制仓位；{relay_status}，且{fade_status}"
        if action_bias == "防守":
            return f"大环境偏弱，应缩量防守；{relay_status}，且{fade_status}"
        return f"大环境不提供保护，优先放弃追涨接力；{relay_status}，且{fade_status}"

    def build_evidence(self, metrics: MarketEnvironmentMetrics, health_score: float) -> list[str]:
        fade_suffix = "（分钟口径）" if "intraday" in str(metrics.source_version) else "（日频代理）"
        return [
            f"上涨 {metrics.up_count} / 下跌 {metrics.down_count} / 平盘 {metrics.flat_count}",
            f"涨停 {metrics.limit_up_count} / 跌停 {metrics.limit_down_count}；涨跌停比 {metrics.limit_up_down_ratio:.2f}",
            f"昨日涨停股今开红比 {metrics.yesterday_limit_up_open_red_ratio:.2%}；收盘溢价比 {metrics.yesterday_limit_up_premium_ratio:.2%}",
            f"冲高回落占比 {metrics.morning_high_then_fall_ratio:.2%}；日内回落占比 {metrics.intraday_fade_ratio:.2%}{fade_suffix}",
            f"成交额变化 {metrics.market_volume_change_pct:.2f}%；收盘均值代理 {metrics.market_avg_close_pct:.2f}%",
            f"环境总分 {health_score:.2f}",
        ]

    def build_judgement(self, metrics: MarketEnvironmentMetrics) -> MarketEnvironmentJudgement:
        health_score = self.compute_market_health_score(metrics)
        market_bias, action_bias = self.classify_market_bias(health_score)
        breadth_status = self.classify_breadth_status(metrics)
        short_term_status = self.classify_short_term_sentiment_status(metrics)
        relay_status = self.classify_relay_sentiment_status(metrics)
        fade_status = self.classify_intraday_fade_status(metrics)

        return MarketEnvironmentJudgement(
            trade_date=metrics.trade_date,
            market_health_score=health_score,
            market_bias=market_bias,
            breadth_status=breadth_status,
            short_term_sentiment_status=short_term_status,
            relay_sentiment_status=relay_status,
            intraday_fade_status=fade_status,
            action_bias=action_bias,
            conclusion=self.build_conclusion(action_bias, relay_status, fade_status),
            evidence=self.build_evidence(metrics, health_score),
        )
