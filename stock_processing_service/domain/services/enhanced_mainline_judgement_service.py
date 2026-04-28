from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

# ── Dataclasses (inlined from stock_service.models to avoid cross‑chain dependency) ──

@dataclass(frozen=True)
class ThemeMainlineJudgement:
    trade_date: str
    subject_key: str
    theme_name: str
    event_chain_score: float
    event_chain_continuity_score: float
    market_recognition_score: float
    mainline_stability_score: float
    is_main_theme: bool
    theme_tier: str
    limit_up_count: int
    conclusion: str
    novelty_score: float = 0.0
    timing_score: float = 0.0
    influence_score: float = 0.0
    capital_persistence_score: float = 0.0
    institution_participation_score: float = 0.0
    retail_attention_score: float = 0.0
    evidence_logic: List[str] = field(default_factory=list)
    evidence_market: List[str] = field(default_factory=list)
    source_type: str = "p3.phase2.mainline"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "theme_mainline_judgement.v1"
    rule_version: str = "theme_mainline_judgement.v1"


# ── Constants ──

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


# ── Input dataclasses (from mainline_judgement_service.py) ──

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


# ── Utility ──

def _clip(value: float, upper: float = 100.0) -> float:
    return max(0.0, min(upper, round(value, 2)))


# ── Parent class: MainlineJudgementService (1:1 from old chain) ──

class MainlineJudgementService:
    """
    P3.phase2 模块 1：
    围绕"事件链 + 市场承认"生成主线题材判断结果。
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


# ── Enhanced dataclasses ──

@dataclass(frozen=True)
class ThemeEvidenceLayers:
    """四层证据数据"""
    event_driven: Dict[str, Any]
    leader_relay: Dict[str, Any]
    board_structure: Dict[str, Any]
    theme_kline: Dict[str, Any]


@dataclass(frozen=True)
class EnhancedMainlineInputs:
    """增强版主线判定输入"""
    event_stats: ThemeEventStats
    market_stats: ThemeMarketStats
    evidence_layers: ThemeEvidenceLayers


# ── Child class: EnhancedMainlineJudgementService (1:1 from old chain) ──

class EnhancedMainlineJudgementService(MainlineJudgementService):
    """
    增强版主线判定服务
    在原有事件链+市场承认基础上，集成四层证据体系
    保持原有接口兼容，新增增强功能
    """

    def compute_evidence_layers(self, trade_date: date, subject_key: str,
                               event_stats: ThemeEventStats,
                               market_stats: ThemeMarketStats) -> ThemeEvidenceLayers:
        """
        计算四层证据评分
        注意：这是简化实现，实际需要从数据库获取详细数据
        """
        # 1. 事件驱动层
        event_driven = {
            "event_count_3d": self._estimate_event_count_3d(event_stats),
            "event_count_7d": event_stats.recent_event_count,
            "strong_event_count_7d": event_stats.key_event_count,
            "event_recency_days": self._compute_event_recency(event_stats),
            "event_continuity_score": self.compute_event_chain_continuity_score(event_stats),
            "event_strength_score": self.compute_event_chain_score(event_stats),
        }

        # 2. 龙头/接力层
        leader_relay = {
            "leader_alive_score": self._compute_leader_alive_score(market_stats),
            "relay_strength_score": self._compute_relay_strength_score(market_stats),
            "front_row_survival_ratio": self._estimate_front_row_survival(market_stats),
        }

        # 3. 板块结构层
        board_structure = {
            "board_stock_count": market_stats.member_count,
            "limit_up_count": market_stats.limit_up_count,
            "red_ratio": self._compute_red_ratio(market_stats),
            "front_row_strength_score": self._compute_front_row_strength(market_stats),
        }

        # 4. 板块K线技术层
        theme_kline = {
            "theme_ret_3d": self._estimate_theme_return_3d(trade_date, subject_key),
            "theme_support_score": self._compute_theme_support_score(trade_date, subject_key),
        }

        return ThemeEvidenceLayers(
            event_driven=event_driven,
            leader_relay=leader_relay,
            board_structure=board_structure,
            theme_kline=theme_kline
        )

    def compute_mainline_strength_score(self, evidence_layers: ThemeEvidenceLayers) -> float:
        """
        计算主线强度评分（0-100）
        基于四层证据加权计算
        """
        weights = {
            "event_driven": 0.3,
            "leader_relay": 0.3,
            "board_structure": 0.25,
            "theme_kline": 0.15
        }

        # 各层评分（简化计算，实际需归一化）
        event_score = min(evidence_layers.event_driven.get("event_strength_score", 0) * 1.2, 100)
        leader_score = min(evidence_layers.leader_relay.get("leader_alive_score", 0) * 1.5, 100)
        board_score = min(evidence_layers.board_structure.get("front_row_strength_score", 0) * 1.3, 100)
        kline_score = min(evidence_layers.theme_kline.get("theme_support_score", 0) * 1.1, 100)

        # 加权总分
        total_score = (
            event_score * weights["event_driven"] +
            leader_score * weights["leader_relay"] +
            board_score * weights["board_structure"] +
            kline_score * weights["theme_kline"]
        )

        return min(max(total_score, 0.0), 100.0)

    def determine_mainline_alive(self, is_main_theme: bool,
                                evidence_layers: ThemeEvidenceLayers,
                                strength_score: float) -> bool:
        """
        判断主线是否存活
        基于设计方案中的公式：主线存活 = 主线题材 + 强度≥60 + 龙头存活≥40 + 3日内有事件
        """
        if not is_main_theme:
            return False

        if strength_score < 60:
            return False

        leader_alive = evidence_layers.leader_relay.get("leader_alive_score", 0)
        if leader_alive < 40:
            return False

        event_count_3d = evidence_layers.event_driven.get("event_count_3d", 0)
        if event_count_3d < 1:
            return False

        return True

    def build_enhanced_judgement(self, trade_date: str,
                                 event_stats: ThemeEventStats,
                                 market_stats: ThemeMarketStats,
                                 evidence_layers: Optional[ThemeEvidenceLayers] = None) -> ThemeMainlineJudgement:
        """
        构建增强版主线判定结果
        保持原有接口，增加增强字段
        """
        # 1. 使用原有逻辑构建基础判定
        base_judgement = super().build_judgement(trade_date, event_stats, market_stats)

        # 2. 计算证据层（如果未提供）
        if evidence_layers is None:
            trade_date_obj = date.fromisoformat(trade_date)
            evidence_layers = self.compute_evidence_layers(trade_date_obj, event_stats.subject_key,
                                                          event_stats, market_stats)

        # 3. 计算增强评分
        strength_score = self.compute_mainline_strength_score(evidence_layers)
        mainline_alive = self.determine_mainline_alive(
            base_judgement.is_main_theme, evidence_layers, strength_score
        )

        # 4. 构建增强结果
        enhanced_dict = base_judgement.__dict__.copy()

        # 添加增强字段（通过source_trace存储，保持模型兼容）
        enhanced_trace = enhanced_dict.get("source_trace", {}).copy()
        enhanced_trace.update({
            "evidence_layers": {
                "event_driven": evidence_layers.event_driven,
                "leader_relay": evidence_layers.leader_relay,
                "board_structure": evidence_layers.board_structure,
                "theme_kline": evidence_layers.theme_kline,
            },
            "mainline_strength_score": strength_score,
            "mainline_alive": mainline_alive,
        })

        enhanced_dict["source_trace"] = enhanced_trace
        enhanced_dict["source_version"] = "theme_mainline_judgement.enhanced.v1"

        return ThemeMainlineJudgement(**enhanced_dict)

    # ===== 辅助方法（简化实现，实际需从数据库获取） =====

    def _estimate_event_count_3d(self, event_stats: ThemeEventStats) -> int:
        """估计3日内事件数量（简化：假设每日平均）"""
        if event_stats.distinct_event_days == 0:
            return 0
        avg_per_day = event_stats.recent_event_count / max(event_stats.distinct_event_days, 1)
        return min(int(avg_per_day * 3), event_stats.recent_event_count)

    def _compute_event_recency(self, event_stats: ThemeEventStats) -> int:
        """计算事件最近性（最近事件距离今天天数）"""
        # 简化：如果有当日事件，则最近性为0
        return 0 if event_stats.today_event_count > 0 else 1

    def _compute_leader_alive_score(self, market_stats: ThemeMarketStats) -> float:
        """计算龙头存活评分"""
        score = 0.0
        if market_stats.leader_limit_up:
            score += 60.0
        if market_stats.leader_pct_chg >= 5:
            score += 30.0
        if market_stats.leader_pct_chg >= 0:
            score += 10.0
        return min(score, 100.0)

    def _compute_relay_strength_score(self, market_stats: ThemeMarketStats) -> float:
        """计算接力强度评分"""
        if market_stats.strong_stock_count >= 3:
            return 70.0
        elif market_stats.strong_stock_count >= 1:
            return 40.0
        else:
            return 20.0

    def _estimate_front_row_survival(self, market_stats: ThemeMarketStats) -> float:
        """估计前排存活率（简化）"""
        if market_stats.member_count == 0:
            return 0.0
        strong_ratio = market_stats.strong_stock_count / market_stats.member_count
        return min(strong_ratio, 1.0)

    def _compute_red_ratio(self, market_stats: ThemeMarketStats) -> float:
        """计算红盘率（简化：假设强势股占比）"""
        if market_stats.member_count == 0:
            return 0.0
        # 简化：涨停和强势股视为红盘
        red_count = market_stats.limit_up_count + max(0, market_stats.strong_stock_count - market_stats.limit_up_count)
        return min(red_count / market_stats.member_count, 1.0)

    def _compute_front_row_strength(self, market_stats: ThemeMarketStats) -> float:
        """计算前排强度"""
        score = 0.0
        score += min(market_stats.limit_up_count * 15.0, 60.0)
        score += min(market_stats.strong_stock_count * 5.0, 30.0)
        if market_stats.leader_limit_up:
            score += 10.0
        return min(score, 100.0)

    def _estimate_theme_return_3d(self, trade_date: date, subject_key: str) -> float:
        """估计主题3日收益率（简化：返回0，实际需查数据库）"""
        # TODO: 从数据库查询主题K线数据
        return 0.0

    def _compute_theme_support_score(self, trade_date: date, subject_key: str) -> float:
        """计算主题支撑评分（简化）"""
        # TODO: 从数据库查询支撑压力数据
        return 50.0


# ── Compatibility wrapper ──

def build_mainline_judgement(trade_date: str,
                             event_stats: ThemeEventStats,
                             market_stats: ThemeMarketStats,
                             enhanced: bool = False) -> ThemeMainlineJudgement:
    """
    兼容性包装函数
    enhanced=True时使用增强版，否则使用原版
    """
    if enhanced:
        service = EnhancedMainlineJudgementService()
        return service.build_enhanced_judgement(trade_date, event_stats, market_stats)
    else:
        service = MainlineJudgementService()
        return service.build_judgement(trade_date, event_stats, market_stats)
