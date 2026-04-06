from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from stock_service.models import ThemeMainlineJudgement


KEY_EVENT_KEYWORDS = (
    "政策",
    "行动计划",
    "印发",
    "试验",
    "商用",
    "首飞",
    "发射",
    "订单",
    "量产",
    "投产",
    "ipo",
    "募股",
    "商业化",
    "里程碑",
)


@dataclass(frozen=True)
class ThemeEventStats:
    subject_key: str
    theme_name: str
    today_event_count: int
    recent_event_count: int
    distinct_event_days: int
    key_event_count: int
    sample_summaries: list[str]


@dataclass(frozen=True)
class ThemeMarketStats:
    subject_key: str
    theme_name: str
    limit_up_count: int
    strong_stock_count: int
    leader_pct_chg: float
    member_count: int
    leader_limit_up: bool


def _clip(value: float, upper: float = 100.0) -> float:
    return max(0.0, min(upper, round(value, 2)))


class MainlineJudgementService:
    """
    P3.phase2 模块 1：
    围绕“事件链 + 市场承认”生成主线题材判断结果。
    """

    def compute_event_chain_score(self, stats: ThemeEventStats) -> float:
        score = 0.0
        score += min(stats.today_event_count, 3) * 12.0
        score += min(stats.recent_event_count, 6) * 5.0
        score += min(stats.key_event_count, 4) * 8.0
        score += min(stats.distinct_event_days, 5) * 4.0
        return _clip(score)

    def compute_event_chain_continuity_score(self, stats: ThemeEventStats) -> float:
        score = 0.0
        score += min(stats.distinct_event_days, 5) * 15.0
        score += max(0, stats.recent_event_count - stats.today_event_count) * 2.0
        if stats.distinct_event_days >= 3:
            score += 10.0
        return _clip(score)

    def compute_market_recognition_score(self, stats: ThemeMarketStats) -> float:
        score = 0.0
        score += min(stats.limit_up_count, 8) * 8.0
        score += min(stats.strong_stock_count, 10) * 2.0
        score += min(max(stats.leader_pct_chg, 0.0), 20.0) * 0.9
        if stats.leader_limit_up:
            score += 12.0
        if stats.member_count >= 5:
            score += 8.0
        return _clip(score)

    def compute_mainline_stability_score(self, event_stats: ThemeEventStats, market_stats: ThemeMarketStats) -> float:
        score = 0.0
        score += min(event_stats.distinct_event_days, 5) * 10.0
        score += min(market_stats.limit_up_count, 6) * 5.0
        score += min(market_stats.strong_stock_count, 8) * 2.5
        if market_stats.leader_limit_up:
            score += 10.0
        if event_stats.recent_event_count >= 3:
            score += 8.0
        return _clip(score)

    def classify_theme_tier(
        self,
        *,
        event_chain_score: float,
        event_chain_continuity_score: float,
        market_recognition_score: float,
        mainline_stability_score: float,
    ) -> tuple[bool, str, str]:
        event_total = event_chain_score + event_chain_continuity_score
        if (
            event_total >= 35.0
            and market_recognition_score >= 60.0
            and mainline_stability_score >= 45.0
        ) or (
            event_total >= 30.0
            and market_recognition_score >= 75.0
            and mainline_stability_score >= 55.0
        ):
            return True, "main", "事件链与市场承认同时成立，具备主线条件"
        if (
            event_total >= 20.0 and market_recognition_score >= 35.0
        ) or market_recognition_score >= 45.0:
            return False, "strong_branch", "存在较强驱动或市场承认，但尚未达到主线强度"
        return False, "failed", "驱动或市场承认不足，暂不建议按主线参与"

    def build_evidence_logic(self, stats: ThemeEventStats) -> list[str]:
        evidence = [
            f"当日事件 {stats.today_event_count} 条",
            f"近 7 日事件 {stats.recent_event_count} 条，覆盖 {stats.distinct_event_days} 天",
        ]
        if stats.key_event_count:
            evidence.append(f"关键事件 {stats.key_event_count} 条")
        for summary in stats.sample_summaries[:3]:
            evidence.append(summary[:80])
        return evidence

    def build_evidence_market(self, stats: ThemeMarketStats) -> list[str]:
        evidence = [
            f"当日涨停 {stats.limit_up_count} 家",
            f"强势股 {stats.strong_stock_count} 家",
            f"龙头涨幅 {stats.leader_pct_chg:.2f}%",
        ]
        if stats.leader_limit_up:
            evidence.append("龙头涨停，板块旗杆成立")
        if stats.member_count >= 5:
            evidence.append(f"板块联动个股 {stats.member_count} 家")
        return evidence

    def build_judgement(
        self,
        trade_date: str,
        event_stats: ThemeEventStats,
        market_stats: ThemeMarketStats,
    ) -> ThemeMainlineJudgement:
        event_chain_score = self.compute_event_chain_score(event_stats)
        continuity_score = self.compute_event_chain_continuity_score(event_stats)
        market_score = self.compute_market_recognition_score(market_stats)
        stability_score = self.compute_mainline_stability_score(event_stats, market_stats)
        is_main_theme, theme_tier, conclusion = self.classify_theme_tier(
            event_chain_score=event_chain_score,
            event_chain_continuity_score=continuity_score,
            market_recognition_score=market_score,
            mainline_stability_score=stability_score,
        )
        return ThemeMainlineJudgement(
            trade_date=trade_date,
            subject_key=event_stats.subject_key,
            theme_name=event_stats.theme_name or market_stats.theme_name,
            event_chain_score=event_chain_score,
            event_chain_continuity_score=continuity_score,
            market_recognition_score=market_score,
            mainline_stability_score=stability_score,
            is_main_theme=is_main_theme,
            theme_tier=theme_tier,
            limit_up_count=market_stats.limit_up_count,
            conclusion=conclusion,
            evidence_logic=self.build_evidence_logic(event_stats),
            evidence_market=self.build_evidence_market(market_stats),
        )

    @staticmethod
    def count_key_events(summaries: Iterable[str]) -> int:
        count = 0
        for summary in summaries:
            lowered = str(summary).lower()
            if any(keyword in lowered for keyword in KEY_EVENT_KEYWORDS):
                count += 1
        return count
