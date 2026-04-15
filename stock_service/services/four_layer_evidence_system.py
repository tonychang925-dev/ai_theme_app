from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import date


@dataclass
class EventLayerEvidence:
    """事件驱动层证据"""
    subject_key: str
    trade_date: date
    event_chain_score: float = 0.0  # 事件链分数（0-100）
    event_chain_continuity_score: float = 0.0  # 事件连续性分数（0-100）
    has_new_event: bool = False  # 当日是否有新事件
    event_importance: float = 0.0  # 事件重要性（0-100）
    media_coverage: float = 0.0  # 媒体报道热度（0-100）

    def total_score(self) -> float:
        """事件驱动层总分（0-100）"""
        return min(100.0,
                  self.event_chain_score * 0.4 +
                  self.event_chain_continuity_score * 0.3 +
                  (100.0 if self.has_new_event else 0.0) * 0.2 +
                  self.event_importance * 0.1)


@dataclass
class LeaderLayerEvidence:
    """龙头/接力层证据"""
    subject_key: str
    trade_date: date
    leader_status: str = ""  # 龙头状态：涨停、强势、走弱、跌停
    leader_pct_chg: float = 0.0  # 龙头涨幅
    leader_limit_up: bool = False  # 龙头是否涨停
    has_successor: bool = False  # 是否有接力卡位
    successor_limit_up_count: int = 0  # 接力涨停数量
    leader_consecutive_days: int = 0  # 龙头连续强势天数

    def total_score(self) -> float:
        """龙头层总分（0-100）"""
        score = 0.0
        if self.leader_limit_up:
            score += 50.0
        elif self.leader_pct_chg >= 5.0:
            score += 30.0
        elif self.leader_pct_chg >= 0.0:
            score += 15.0

        if self.has_successor:
            score += 25.0

        score += min(self.successor_limit_up_count * 10.0, 30.0)
        score += min(self.leader_consecutive_days * 5.0, 20.0)

        return min(score, 100.0)


@dataclass
class BoardStructureEvidence:
    """板块结构层证据"""
    subject_key: str
    trade_date: date
    limit_up_count: int = 0  # 涨停数量
    strong_stock_count: int = 0  # 强势股数量
    member_count: int = 0  # 板块成员数量
    has_limit_up_梯队: bool = False  # 是否有涨停梯队
    has_followers: bool = False  # 是否有跟风股
    red_ratio: float = 0.0  # 红盘比例

    def total_score(self) -> float:
        """板块结构层总分（0-100）"""
        score = 0.0

        # 涨停数量评分
        if self.limit_up_count >= 10:
            score += 40.0
        elif self.limit_up_count >= 5:
            score += 30.0
        elif self.limit_up_count >= 3:
            score += 20.0
        elif self.limit_up_count >= 1:
            score += 10.0

        # 强势股数量评分
        if self.strong_stock_count >= 20:
            score += 30.0
        elif self.strong_stock_count >= 10:
            score += 20.0
        elif self.strong_stock_count >= 5:
            score += 15.0
        elif self.strong_stock_count >= 2:
            score += 5.0

        # 梯队和跟风
        if self.has_limit_up_梯队:
            score += 15.0
        if self.has_followers:
            score += 10.0

        # 红盘比例
        score += self.red_ratio * 0.5  # 0-50分

        return min(score, 100.0)


@dataclass
class KLineEvidence:
    """板块K线技术层证据"""
    subject_key: str
    trade_date: date
    board_pct_chg: float = 0.0  # 板块指数涨跌幅
    board_red_days: int = 0  # 板块连续红盘天数
    board_volume_ratio: float = 1.0  # 板块成交量比（较前一日）
    has_support: bool = False  # 是否有技术支撑
    has_resistance: bool = False  # 是否有技术阻力
    is_overheated: bool = False  # 是否过热

    def total_score(self) -> float:
        """K线技术层总分（0-100）"""
        score = 0.0

        # 板块涨跌幅
        if self.board_pct_chg >= 5.0:
            score += 30.0
        elif self.board_pct_chg >= 2.0:
            score += 20.0
        elif self.board_pct_chg >= 0.0:
            score += 10.0

        # 连续红盘天数
        score += min(self.board_red_days * 8.0, 25.0)

        # 成交量比
        if self.board_volume_ratio >= 1.5:
            score += 20.0
        elif self.board_volume_ratio >= 1.2:
            score += 15.0
        elif self.board_volume_ratio >= 0.8:
            score += 5.0

        # 技术面
        if self.has_support:
            score += 15.0
        if not self.has_resistance:
            score += 10.0
        if self.is_overheated:
            score -= 20.0

        return max(0.0, min(score, 100.0))


@dataclass
class FourLayerEvidence:
    """四层证据汇总"""
    event_layer: EventLayerEvidence
    leader_layer: LeaderLayerEvidence
    board_layer: BoardStructureEvidence
    kline_layer: KLineEvidence

    def overall_score(self) -> float:
        """综合评分（0-100）"""
        weights = {
            "event": 0.25,    # 事件驱动层权重
            "leader": 0.30,   # 龙头层权重（最重要）
            "board": 0.30,    # 板块结构层权重
            "kline": 0.15,    # K线技术层权重
        }

        return (
            self.event_layer.total_score() * weights["event"] +
            self.leader_layer.total_score() * weights["leader"] +
            self.board_layer.total_score() * weights["board"] +
            self.kline_layer.total_score() * weights["kline"]
        )

    def has_hard_fade_evidence(self) -> bool:
        """
        检查是否满足退潮硬证据
        根据用户定义的标准：
        1. 龙头已死（龙头跌停或大幅下跌）
        2. 市场再也没有持续消息刺激（事件链分数低）
        3. 板块出现大面积跌停或板块K线明显回落到低谷
        4. 龙头倒下后没有接力和卡位
        5. 板块整体技术形态走坏
        """
        # 1. 龙头已死
        leader_dead = (self.leader_layer.leader_pct_chg <= -5.0 or
                      self.leader_layer.leader_status in ["跌停", "走弱"])

        # 2. 事件链断裂
        event_chain_broken = self.event_layer.total_score() < 20.0

        # 3. 板块塌方
        board_collapse = (self.board_layer.limit_up_count == 0 and
                         self.board_layer.strong_stock_count <= 2)

        # 4. 无接力卡位
        no_successor = not self.leader_layer.has_successor

        # 5. 技术形态走坏
        technical_broken = (self.kline_layer.board_pct_chg < -2.0 and
                           not self.kline_layer.has_support)

        # 需要至少3项硬证据才判断为退潮
        hard_evidence_count = sum([
            leader_dead,
            event_chain_broken,
            board_collapse,
            no_successor,
            technical_broken
        ])

        return hard_evidence_count >= 3

    def is_mainline_alive(self) -> bool:
        """判断主线是否存活"""
        # 主线存活的条件：综合评分≥40且不满足退潮硬证据
        return self.overall_score() >= 40.0 and not self.has_hard_fade_evidence()

    def determine_cycle_state(self) -> str:
        """基于四层证据判断周期状态"""
        overall = self.overall_score()
        has_hard_fade = self.has_hard_fade_evidence()

        if has_hard_fade:
            return "fade"

        # 根据综合评分和分层证据判断状态
        if overall >= 80.0:
            if self.board_layer.limit_up_count >= 10:
                return "climax"
            else:
                return "fermentation"
        elif overall >= 60.0:
            return "acceleration"
        elif overall >= 45.0:
            # 检查是否有分歧特征
            if (self.leader_layer.leader_limit_up and
                self.board_layer.limit_up_count <= 2):
                return "divergence"
            else:
                return "fermentation"
        elif overall >= 35.0:
            return "divergence"
        elif overall >= 25.0:
            return "repair"
        else:
            return "start"


class FourLayerEvidenceSystem:
    """四层证据体系"""

    @staticmethod
    def build_from_inputs(
        subject_key: str,
        trade_date: date,
        mainline_input,  # ThemeCycleMainlineInput
        market_input,    # ThemeCycleMarketInput
        recent_input,    # ThemeCycleRecentInput
        additional_data: Optional[Dict] = None
    ) -> FourLayerEvidence:
        """从现有输入构建四层证据"""

        # 事件驱动层
        event_layer = EventLayerEvidence(
            subject_key=subject_key,
            trade_date=trade_date,
            event_chain_score=mainline_input.event_chain_score,
            event_chain_continuity_score=mainline_input.event_chain_continuity_score,
            has_new_event=False,  # 需要从事件表查询
            event_importance=0.0,
            media_coverage=0.0
        )

        # 龙头/接力层
        leader_layer = LeaderLayerEvidence(
            subject_key=subject_key,
            trade_date=trade_date,
            leader_status="",  # 需要从市场数据推导
            leader_pct_chg=market_input.leader_pct_chg,
            leader_limit_up=market_input.leader_limit_up,
            has_successor=False,  # 需要分析板块结构
            successor_limit_up_count=0,
            leader_consecutive_days=0
        )

        # 板块结构层
        board_layer = BoardStructureEvidence(
            subject_key=subject_key,
            trade_date=trade_date,
            limit_up_count=market_input.limit_up_count,
            strong_stock_count=market_input.strong_stock_count,
            member_count=market_input.member_count,
            has_limit_up_梯队=False,  # 需要分析涨停梯队
            has_followers=False,  # 需要分析跟风股
            red_ratio=0.0  # 需要从个股数据计算
        )

        # K线技术层（简化，需要更多数据）
        kline_layer = KLineEvidence(
            subject_key=subject_key,
            trade_date=trade_date,
            board_pct_chg=0.0,  # 需要板块指数数据
            board_red_days=recent_input.recent_red_days,
            board_volume_ratio=1.0,
            has_support=False,
            has_resistance=False,
            is_overheated=False
        )

        return FourLayerEvidence(
            event_layer=event_layer,
            leader_layer=leader_layer,
            board_layer=board_layer,
            kline_layer=kline_layer
        )