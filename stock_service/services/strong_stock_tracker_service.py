#!/usr/bin/env python3
"""
强势股清单跟踪服务

功能：
1. 维护一周内的强势股清单（龙头、强势股）
2. 结合主线逻辑，从强势股中筛选候选
3. 检测前一日弱势、今日资金流入/异动/技术支撑位
4. 生成次日重点观察对象列表

逻辑流程：
1. 从每日主题数据（ThemeCycleJudgement, ThemeLeaderCandidate等）识别强势股
2. 更新强势股清单，记录标记日期和原因
3. 对于清单中的股票，检查前一日是否弱势（大阴线、上引线、烂板）
4. 检查今日是否有资金流入、异动行为或技术形态到支撑位
5. 标记为次日重点观察对象
"""

import asyncio
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from stock_service.models import (
    StrongStockRecord,
    StrongStockList,
    ThemeCycleJudgement,
    ThemeLeaderCandidate,
    ThemeMainlineJudgement,
    StockAbnormalSignal,
    MarketEnvironmentJudgement,
)
from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongDetectionInputs

logger = logging.getLogger(__name__)


class StrongStockTrackerService:
    """强势股清单跟踪服务"""

    def __init__(self, weak_to_strong_service: Optional[WeakToStrongService] = None):
        self.weak_to_strong_service = weak_to_strong_service or WeakToStrongService()
        self._strong_stocks: Dict[str, StrongStockRecord] = {}  # stock_id -> record
        self._strong_stocks_by_date: Dict[str, List[StrongStockRecord]] = defaultdict(list)
        self._weak_to_strong_candidates: List[StrongStockRecord] = []
        self._next_day_focus_stocks: List[StrongStockRecord] = []

    async def update_strong_stock_list(
        self,
        trade_date: date,
        theme_judgements: List[ThemeCycleJudgement],
        leader_candidates: List[ThemeLeaderCandidate],
        mainline_judgements: List[ThemeMainlineJudgement],
        abnormal_signals: List[StockAbnormalSignal],
        market_environment: Optional[MarketEnvironmentJudgement] = None
    ) -> StrongStockList:
        """
        更新强势股清单

        Args:
            trade_date: 交易日
            theme_judgements: 主题周期判断列表
            leader_candidates: 龙头候选列表
            mainline_judgements: 主线判断列表
            abnormal_signals: 异常信号列表
            market_environment: 市场环境判断

        Returns:
            更新后的强势股清单
        """
        logger.info(f"更新强势股清单，交易日: {trade_date}")

        # 1. 识别强势股（从主线主题中）
        mainline_themes = self._get_mainline_themes(mainline_judgements)
        strong_stocks_today = await self._identify_strong_stocks(
            trade_date, theme_judgements, leader_candidates, mainline_themes, abnormal_signals
        )

        # 2. 更新全局强势股记录
        updated_records = self._update_strong_stock_records(trade_date, strong_stocks_today)

        # 3. 清理过期记录（超过7天）
        self._cleanup_expired_records(trade_date)

        # 4. 筛选弱转强候选
        weak_to_strong_candidates = await self._screen_weak_to_strong_candidates(
            trade_date, updated_records, abnormal_signals, market_environment
        )
        self._weak_to_strong_candidates = weak_to_strong_candidates

        # 5. 识别次日重点观察对象
        next_day_focus_stocks = await self._identify_next_day_focus_stocks(
            trade_date, weak_to_strong_candidates, abnormal_signals
        )
        self._next_day_focus_stocks = next_day_focus_stocks

        # 6. 构建清单
        strong_stock_list = StrongStockList(
            trade_date=trade_date.isoformat(),
            strong_stocks=updated_records,
            previous_days_stocks=dict(self._strong_stocks_by_date),
            candidate_count=len(weak_to_strong_candidates),
            weak_to_strong_candidates=weak_to_strong_candidates,
            next_day_focus_stocks=next_day_focus_stocks
        )

        logger.info(f"强势股清单更新完成: {len(updated_records)}只强势股, "
                   f"{len(weak_to_strong_candidates)}只弱转强候选, "
                   f"{len(next_day_focus_stocks)}只次日重点观察")

        return strong_stock_list

    def _get_mainline_themes(self, mainline_judgements: List[ThemeMainlineJudgement]) -> Set[str]:
        """获取主线主题集合"""
        mainline_themes = set()
        for judgement in mainline_judgements:
            if judgement.is_main_theme:
                mainline_themes.add(judgement.theme_name)
        return mainline_themes

    async def _identify_strong_stocks(
        self,
        trade_date: date,
        theme_judgements: List[ThemeCycleJudgement],
        leader_candidates: List[ThemeLeaderCandidate],
        mainline_themes: Set[str],
        abnormal_signals: List[StockAbnormalSignal]
    ) -> List[StrongStockRecord]:
        """识别强势股"""
        strong_stocks = []

        # 从龙头候选识别
        for candidate in leader_candidates:
            # 检查是否属于主线主题
            if candidate.theme_name not in mainline_themes:
                continue

            # 检查是否龙头或强势
            if candidate.composite_score >= 70 or candidate.role_label in ["龙头", "前排"]:
                # 创建强势股记录
                record = StrongStockRecord(
                    stock_id=candidate.stock_id,
                    stock_name=candidate.stock_name,
                    theme_name=candidate.theme_name,
                    dragon_head_level=self._determine_dragon_head_level(candidate),
                    strong_reason=f"龙头候选评分{candidate.composite_score:.1f}",
                    first_marked_date=trade_date.isoformat(),
                    last_marked_date=trade_date.isoformat(),
                    marked_days_count=1,
                    last_day_data=None  # 后续填充
                )
                strong_stocks.append(record)

        # 从主题周期判断识别（周期阶段强势的股票）
        for judgement in theme_judgements:
            # 检查是否属于主线主题
            if judgement.theme_name not in mainline_themes:
                continue

            # 检查是否强势阶段
            if judgement.is_main_theme and judgement.primary_cycle_stage in ["fermentation", "climax", "rebound"]:
                # 从subject_key提取股票信息（简化处理）
                stock_id = self._extract_stock_id_from_subject(judgement.subject_key)
                if stock_id:
                    # 查找对应的龙头候选获取更多信息
                    candidate_info = next(
                        (c for c in leader_candidates if c.stock_id == stock_id),
                        None
                    )

                    record = StrongStockRecord(
                        stock_id=stock_id,
                        stock_name=candidate_info.stock_name if candidate_info else judgement.subject_key,
                        theme_name=judgement.theme_name,
                        dragon_head_level="relative" if judgement.leader_status else "sector",
                        strong_reason=f"主题周期阶段: {judgement.primary_cycle_stage}",
                        first_marked_date=trade_date.isoformat(),
                        last_marked_date=trade_date.isoformat(),
                        marked_days_count=1,
                        last_day_data=None
                    )
                    strong_stocks.append(record)

        # 从异常信号识别（有强势异动的股票）
        abnormal_stocks = self._identify_strong_stocks_from_abnormal_signals(
            trade_date, abnormal_signals, mainline_themes
        )
        strong_stocks.extend(abnormal_stocks)

        return strong_stocks

    def _determine_dragon_head_level(self, candidate: ThemeLeaderCandidate) -> str:
        """确定龙头级别"""
        if candidate.role_label == "龙头":
            return "absolute"
        elif candidate.role_label == "前排":
            return "relative"
        elif candidate.composite_score >= 80:
            return "relative"
        else:
            return "sector"

    def _extract_stock_id_from_subject(self, subject_key: str) -> Optional[str]:
        """从subject_key提取股票ID"""
        import re
        # 匹配股票代码模式：6位数字
        match = re.search(r'(\d{6})', subject_key)
        if match:
            stock_code = match.group(1)
            # 确定后缀
            if stock_code.startswith('6'):
                suffix = 'SH'
            elif stock_code.startswith('0') or stock_code.startswith('3'):
                suffix = 'SZ'
            else:
                suffix = 'SZ'
            return f"{stock_code}.{suffix}"
        return None

    def _identify_strong_stocks_from_abnormal_signals(
        self,
        trade_date: date,
        abnormal_signals: List[StockAbnormalSignal],
        mainline_themes: Set[str]
    ) -> List[StrongStockRecord]:
        """从异常信号识别强势股"""
        strong_stocks = []

        for signal in abnormal_signals:
            # 检查是否属于主线主题（简化：检查subject_key是否包含主题信息）
            # 实际中需要更多主题-股票映射信息

            # 检查强势信号
            is_strong_signal = (
                getattr(signal, 'is_limit_up', False) or
                getattr(signal, 'pct_chg', 0) > 5.0 or
                getattr(signal, 'has_hot_money_buy', False) or
                getattr(signal, 'has_institution_buy', False)
            )

            if is_strong_signal:
                record = StrongStockRecord(
                    stock_id=signal.stock_id,
                    stock_name=signal.stock_name or signal.stock_id,
                    theme_name=signal.theme_name or "未知主题",
                    dragon_head_level="sector",
                    strong_reason=f"异常信号: {signal.abnormal_type}",
                    first_marked_date=trade_date.isoformat(),
                    last_marked_date=trade_date.isoformat(),
                    marked_days_count=1,
                    last_day_data=None
                )
                strong_stocks.append(record)

        return strong_stocks

    def _update_strong_stock_records(
        self,
        trade_date: date,
        today_strong_stocks: List[StrongStockRecord]
    ) -> List[StrongStockRecord]:
        """更新强势股记录"""
        updated_records = []

        for today_record in today_strong_stocks:
            stock_id = today_record.stock_id

            if stock_id in self._strong_stocks:
                # 更新现有记录
                existing = self._strong_stocks[stock_id]
                existing.last_marked_date = trade_date.isoformat()
                existing.marked_days_count += 1
                existing.updated_at = datetime.now().isoformat()
                updated_records.append(existing)
            else:
                # 添加新记录
                self._strong_stocks[stock_id] = today_record
                updated_records.append(today_record)

        # 添加到日期分组
        date_key = trade_date.isoformat()
        self._strong_stocks_by_date[date_key] = updated_records

        return updated_records

    def _cleanup_expired_records(self, current_date: date):
        """清理过期记录（超过7天未标记）"""
        expired_days = 7
        cutoff_date = current_date - timedelta(days=expired_days)
        cutoff_str = cutoff_date.isoformat()

        expired_stocks = []
        for stock_id, record in list(self._strong_stocks.items()):
            if record.last_marked_date < cutoff_str:
                expired_stocks.append(stock_id)

        for stock_id in expired_stocks:
            del self._strong_stocks[stock_id]

        # 清理日期分组
        for date_key in list(self._strong_stocks_by_date.keys()):
            if date_key < cutoff_str:
                del self._strong_stocks_by_date[date_key]

        if expired_stocks:
            logger.info(f"清理过期强势股记录: {len(expired_stocks)}只")

    async def _screen_weak_to_strong_candidates(
        self,
        trade_date: date,
        strong_stocks: List[StrongStockRecord],
        abnormal_signals: List[StockAbnormalSignal],
        market_environment: Optional[MarketEnvironmentJudgement] = None
    ) -> List[StrongStockRecord]:
        """筛选弱转强候选"""
        candidates = []

        for record in strong_stocks:
            # 检查是否满足弱转强条件
            is_candidate = await self._check_weak_to_strong_conditions(
                trade_date, record, abnormal_signals, market_environment
            )

            if is_candidate:
                record.weak_to_strong_candidate = True
                candidates.append(record)

        return candidates

    async def _check_weak_to_strong_conditions(
        self,
        trade_date: date,
        record: StrongStockRecord,
        abnormal_signals: List[StockAbnormalSignal],
        market_environment: Optional[MarketEnvironmentJudgement] = None
    ) -> bool:
        """检查弱转强条件"""
        # 1. 前一日是否弱势（需要前一日数据）
        # 2. 今日是否有资金流入或异动
        # 3. 是否有技术支撑位

        # 查找该股票的异常信号
        stock_signals = [
            s for s in abnormal_signals
            if s.stock_id == record.stock_id
        ]

        if not stock_signals:
            return False

        latest_signal = stock_signals[0]  # 假设按日期排序

        # 检查前一日弱势特征（需要前一日K线数据）
        # 这里简化处理：检查信号中是否有弱势标记
        prev_day_weak = getattr(latest_signal, 'is_bad_limit_up', False) or getattr(latest_signal, 'is_upper_shadow', False) or getattr(latest_signal, 'pct_chg', 0) < -2.0

        # 检查今日资金流入/异动
        today_strong = (
            getattr(latest_signal, 'has_hot_money_buy', False) or
            getattr(latest_signal, 'has_institution_buy', False) or
            getattr(latest_signal, 'pct_chg', 0) > 3.0 or
            getattr(latest_signal, 'volume_ratio_to_ma50', 0) > 1.5
        )

        # 检查技术支撑位（需要K线数据，这里简化）
        # 实际中需要访问K线服务

        # 综合判断
        is_candidate = prev_day_weak and today_strong

        return is_candidate

    async def _identify_next_day_focus_stocks(
        self,
        trade_date: date,
        weak_to_strong_candidates: List[StrongStockRecord],
        abnormal_signals: List[StockAbnormalSignal]
    ) -> List[StrongStockRecord]:
        """识别次日重点观察对象"""
        focus_stocks = []

        for candidate in weak_to_strong_candidates:
            # 查找该股票的异常信号
            stock_signals = [
                s for s in abnormal_signals
                if s.stock_id == candidate.stock_id
            ]

            if not stock_signals:
                continue

            latest_signal = stock_signals[0]

            # 判断是否为次日重点观察对象
            # 条件：弱转强候选 + 今日有明显异动 + 有技术支撑位
            has_today_action = (
                getattr(latest_signal, 'has_hot_money_buy', False) or
                getattr(latest_signal, 'has_institution_buy', False) or
                getattr(latest_signal, 'volume_ratio_to_ma50', 0) > 2.0
            )

            if has_today_action:
                candidate.next_day_focus = True
                focus_stocks.append(candidate)

        return focus_stocks

    def get_strong_stocks_by_theme(self, theme_name: str) -> List[StrongStockRecord]:
        """按主题获取强势股"""
        return [
            record for record in self._strong_stocks.values()
            if record.theme_name == theme_name
        ]

    def get_weak_to_strong_candidates(self) -> List[StrongStockRecord]:
        """获取弱转强候选"""
        return self._weak_to_strong_candidates

    def get_next_day_focus_stocks(self) -> List[StrongStockRecord]:
        """获取次日重点观察对象"""
        return self._next_day_focus_stocks

    def clear_all(self):
        """清空所有记录（用于测试）"""
        self._strong_stocks.clear()
        self._strong_stocks_by_date.clear()
        self._weak_to_strong_candidates.clear()
        self._next_day_focus_stocks.clear()
        logger.info("强势股清单已清空")