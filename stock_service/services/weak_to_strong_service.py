#!/usr/bin/env python3
"""
弱转强策略服务
基于'弱转强买入法'PDF文档实现弱转强信号检测和评分
核心逻辑：分歧后的回流、调整后重新走强、关键支撑位反弹
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from stock_service.models import ThemeCycleJudgement, StockAbnormalSignal
from stock_service.services.kline_data_service import KlineDataService

# 技术分析库
try:
    import talib
    import numpy as np
    TA_LIB_AVAILABLE = True
except ImportError:
    TA_LIB_AVAILABLE = False
    talib = None
    np = None

logger = logging.getLogger(__name__)


@dataclass
class WeakToStrongSignal:
    """弱转强信号"""
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str

    # 信号核心特征
    signal_type: str  # "分歧回流", "支撑反弹", "放量转强", "资金回流"
    signal_strength: float  # 信号强度 0-100
    confidence_score: float  # 置信度 0-100

    # 技术特征
    prev_stage: str  # 前一个周期阶段
    current_stage: str  # 当前周期阶段
    action_bias: str  # 操作偏向

    # 量价特征
    volume_ratio: float  # 量比
    turnover_rate: float  # 换手率
    pct_chg: float  # 涨幅
    main_net_inflow: float  # 主力净流入
    is_limit_up: bool  # 是否涨停

    # 形态特征
    is_divergence_rebound: bool  # 是否分歧回流
    is_support_bounce: bool  # 是否支撑反弹
    is_volume_breakout: bool  # 是否放量突破
    has_capital_inflow: bool  # 是否有资金流入

    # 龙头和板块特征
    is_dragon_head: bool = False  # 是否龙头股
    dragon_head_level: str = ""  # 龙头级别：absolute/relative/sector
    has_plate_support: bool = False  # 是否有板块支持
    plate_support_strength: float = 0.0  # 板块支持强度

    # 弱势类型
    weak_type: str = ""  # 弱势类型：big_negative_line/upper_shadow/bad_limit_up
    weak_intensity: float = 0.0  # 弱势强度

    # 分时特征
    intraday_pattern: str = ""  # 分时模式：opening/early/mid/late
    bid_weak_to_strong: bool = False  # 集合竞价弱转强
    early_weak_to_strong: bool = False  # 早盘分时弱转强
    intraday_weak_to_strong: bool = False  # 盘中弱转强

    # 反包特征
    is_engulfing: bool = False  # 是否反包
    engulfing_strength: float = 0.0  # 反包强度
    previous_close_pct: float = 0.0  # 前一日涨跌幅

    # 支撑位特征
    has_support: bool = False  # 是否有支撑位
    support_type: str = ""  # 支撑位类型: gap/ma/fibonacci/previous_low
    support_strength: float = 0.0  # 支撑位强度
    support_level: float = 0.0  # 支撑位价格
    is_gap_support: bool = False  # 是否缺口支撑

    # 证据和结论
    evidence: List[str] = field(default_factory=list)
    conclusion: str = ""
    risk_level: str = "low"  # risk level: low/medium/high

    # 跟踪字段
    source_type: str = "p3.phase3.weak_to_strong_signal"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "weak_to_strong_signal.v1"
    rule_version: str = "weak_to_strong_signal.v1"


@dataclass
class WeakToStrongJudgement:
    """弱转强判断结果"""
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str

    # 综合评分
    weak_to_strong_score: float  # 弱转强综合评分 0-100
    eligibility_score: float  # 入选资格评分 0-100
    timing_score: float  # 时机评分 0-100

    # 信号分析
    primary_signal_type: str
    supporting_signals: List[str]

    # 操作建议
    action_bias: str  # "重点买入", "试错买入", "观察", "回避"
    position_suggestion: float  # 仓位建议 0-1.0
    stop_loss_level: float  # 止损位百分比

    # 详细分析
    signal_analysis: str
    risk_assessment: str
    watch_points: List[str]

    # 证据和结论
    evidence: List[str] = field(default_factory=list)
    conclusion: str = ""

    # 跟踪字段
    source_type: str = "p3.phase3.weak_to_strong_judgement"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "weak_to_strong_judgement.v1"
    rule_version: str = "weak_to_strong_judgement.v1"


@dataclass
class WeakToStrongDetectionInputs:
    """弱转强检测输入数据"""
    cycle_judgement: Optional[ThemeCycleJudgement] = None
    abnormal_signal: Optional[StockAbnormalSignal] = None
    prev_day_data: Optional[Dict[str, Any]] = None
    current_day_data: Optional[Dict[str, Any]] = None
    market_environment: Optional[Dict[str, Any]] = None
    theme_environment: Optional[Dict[str, Any]] = None


class WeakToStrongService:
    """弱转强策略服务（已降级为诊断层）。

    正式主链请使用：
    1. weak_to_strong_candidate_builder（盘后候选）
    2. weak_to_strong_auction_service（盘前确认）
    """

    def __init__(self, db_manager=None, kline_data_service=None):
        self.db_manager = db_manager
        if kline_data_service is None:
            # 创建默认的K线数据服务实例
            from stock_service.services.kline_data_service import KlineDataService
            self.kline_data_service = KlineDataService()
        else:
            self.kline_data_service = kline_data_service

    async def detect_weak_to_strong_signals(
        self,
        trade_date: date,
        inputs: WeakToStrongDetectionInputs
    ) -> List[WeakToStrongSignal]:
        warnings.warn(
            "WeakToStrongService 已降级为诊断/兼容层，不建议用于正式准入链路",
            DeprecationWarning,
            stacklevel=2,
        )
        """
        检测弱转强信号

        弱转强核心特征：
        1. 分歧后的回流：从divergence阶段转为rebound/fermentation阶段
        2. 调整后重新走强：经过调整后出现放量上涨
        3. 支撑位反弹：在关键支撑位出现放量反弹
        4. 资金回流：主力资金从流出转为流入

        Args:
            trade_date: 交易日
            inputs: 输入数据

        Returns:
            弱转强信号列表
        """
        signals = []

        # 获取必要数据
        cycle_judgement = inputs.cycle_judgement
        abnormal_signal = inputs.abnormal_signal

        if not cycle_judgement:
            return signals

        stock_id = getattr(cycle_judgement, 'stock_id', None)
        if not stock_id:
            # 从subject_key尝试推断股票ID
            # 如果subject_key包含股票代码格式（如"002361.SZ"），则使用它
            import re
            subject_key = getattr(cycle_judgement, 'subject_key', '')
            # 匹配股票代码模式：6位数字，可能带有后缀如.SZ/.SH
            match = re.search(r'(\d{6})(?:\.(SZ|SH|BJ))?', subject_key)
            if match:
                stock_code = match.group(1)
                suffix = match.group(2) if match.group(2) else 'SZ'
                stock_id = f"{stock_code}.{suffix}"
            else:
                # 如果无法推断，仍继续处理，可能在_build_weak_to_strong_signal中处理
                stock_id = ''

        # 检查是否为弱转强阶段
        is_weak_to_strong = self._check_weak_to_strong_stage(cycle_judgement)

        if not is_weak_to_strong:
            return signals

        # 构建信号
        signal = await self._build_weak_to_strong_signal(
            trade_date, cycle_judgement, abnormal_signal, inputs
        )

        if signal:
            signals.append(signal)

        return signals

    def _check_weak_to_strong_stage(self, cycle_judgement: ThemeCycleJudgement) -> bool:
        """检查是否为弱转强阶段"""
        # 弱转强的典型阶段：
        # 1. 分歧后回流：is_divergence=True → is_rebound=True
        # 2. 调整后走强：阶段从decline/divergence转为rebound/fermentation

        stage = cycle_judgement.primary_cycle_stage.lower()
        action_bias = cycle_judgement.action_bias

        # 检查阶段特征
        if stage in ["rebound", "fermentation"]:
            # 回流或发酵阶段，可能是弱转强
            pass

        # 检查action_bias是否包含弱转强
        if "弱转强" in action_bias:
            return True

        # 检查周期阶段特征
        if (cycle_judgement.is_divergence and
            (cycle_judgement.is_rebound or cycle_judgement.is_fermentation)):
            return True

        # 检查是否有分歧后回流的特征
        prev_stage = getattr(cycle_judgement, 'prev_stage', '')
        if prev_stage in ["divergence", "decline"] and stage in ["rebound", "fermentation"]:
            return True

        return False

    async def _build_weak_to_strong_signal(
        self,
        trade_date: date,
        cycle_judgement: ThemeCycleJudgement,
        abnormal_signal: Optional[StockAbnormalSignal],
        inputs: WeakToStrongDetectionInputs
    ) -> Optional[WeakToStrongSignal]:
        """构建弱转强信号"""
        try:
            # 确定信号类型
            signal_type = self._determine_signal_type(cycle_judgement, abnormal_signal)

            # 计算信号强度
            signal_strength = self._calculate_signal_strength(
                cycle_judgement, abnormal_signal, inputs
            )

            # 计算置信度
            confidence_score = self._calculate_confidence_score(
                cycle_judgement, abnormal_signal, inputs
            )

            # 获取量价数据
            volume_features = self._extract_volume_features(abnormal_signal, inputs)

            # 分析弱转强特征（基于PDF规则）
            weak_to_strong_features = await self._analyze_weak_to_strong_features(
                cycle_judgement, abnormal_signal, inputs
            )

            # 收集证据（包含技术分析证据）
            evidence = self._collect_evidence(cycle_judgement, abnormal_signal, inputs)
            # 添加技术分析证据（支撑位、缺口等）
            technical_evidence = weak_to_strong_features.get('technical_evidence', [])
            if technical_evidence:
                evidence.extend(technical_evidence)

            # 获取股票信息
            stock_id = getattr(cycle_judgement, 'stock_id', '')
            stock_name = getattr(cycle_judgement, 'stock_name', '')

            # 如果股票名称为空，尝试从其他信息推断
            if not stock_name:
                # 如果subject_key看起来像股票代码，使用主题名称作为股票名称
                import re
                if re.search(r'\d{6}', cycle_judgement.subject_key):
                    # subject_key包含股票代码，使用theme_name作为股票名称
                    stock_name = cycle_judgement.theme_name
                else:
                    # 否则使用subject_key作为股票名称
                    stock_name = cycle_judgement.subject_key

            # 构建信号
            signal = WeakToStrongSignal(
                trade_date=trade_date.isoformat(),
                stock_id=stock_id,
                stock_name=stock_name,
                subject_key=cycle_judgement.subject_key,
                theme_name=cycle_judgement.theme_name,
                signal_type=signal_type,
                signal_strength=signal_strength,
                confidence_score=confidence_score,
                prev_stage=getattr(cycle_judgement, 'prev_stage', ''),
                current_stage=cycle_judgement.primary_cycle_stage,
                action_bias=cycle_judgement.action_bias,
                volume_ratio=volume_features.get('volume_ratio', 0.0),
                turnover_rate=volume_features.get('turnover_rate', 0.0),
                pct_chg=volume_features.get('pct_chg', 0.0),
                main_net_inflow=volume_features.get('main_net_inflow', 0.0),
                is_limit_up=volume_features.get('is_limit_up', False),
                is_divergence_rebound=signal_type == "分歧回流",
                is_support_bounce=signal_type == "支撑反弹",
                is_volume_breakout=volume_features.get('is_volume_breakout', False),
                has_capital_inflow=volume_features.get('has_capital_inflow', False),
                # 龙头和板块特征
                is_dragon_head=weak_to_strong_features.get('is_dragon_head', False),
                dragon_head_level=weak_to_strong_features.get('dragon_head_level', ''),
                has_plate_support=weak_to_strong_features.get('has_plate_support', False),
                plate_support_strength=weak_to_strong_features.get('plate_support_strength', 0.0),
                # 弱势类型
                weak_type=weak_to_strong_features.get('weak_type', ''),
                weak_intensity=weak_to_strong_features.get('weak_intensity', 0.0),
                # 分时特征
                intraday_pattern=weak_to_strong_features.get('intraday_pattern', ''),
                bid_weak_to_strong=weak_to_strong_features.get('bid_weak_to_strong', False),
                early_weak_to_strong=weak_to_strong_features.get('early_weak_to_strong', False),
                intraday_weak_to_strong=weak_to_strong_features.get('intraday_weak_to_strong', False),
                # 反包特征
                is_engulfing=weak_to_strong_features.get('is_engulfing', False),
                engulfing_strength=weak_to_strong_features.get('engulfing_strength', 0.0),
                previous_close_pct=weak_to_strong_features.get('previous_close_pct', 0.0),
                # 支撑位特征
                has_support=weak_to_strong_features.get('has_support', False),
                support_type=weak_to_strong_features.get('support_type', ''),
                support_strength=weak_to_strong_features.get('support_strength', 0.0),
                support_level=weak_to_strong_features.get('support_level', 0.0),
                is_gap_support=weak_to_strong_features.get('is_gap_support', False),
                evidence=evidence,
                conclusion=self._generate_conclusion(signal_type, signal_strength),
                risk_level=self._assess_risk_level(signal_strength, confidence_score)
            )

            return signal

        except Exception as e:
            logger.error(f"构建弱转强信号失败: {e}")
            return None

    def _determine_signal_type(
        self,
        cycle_judgement: ThemeCycleJudgement,
        abnormal_signal: Optional[StockAbnormalSignal]
    ) -> str:
        """确定信号类型"""
        stage = cycle_judgement.primary_cycle_stage.lower()
        prev_stage = getattr(cycle_judgement, 'prev_stage', '')
        action_bias = cycle_judgement.action_bias

        if "弱转强" in action_bias:
            return "弱转强"

        if prev_stage in ["divergence", "decline"] and stage in ["rebound", "fermentation"]:
            return "分歧回流"

        if abnormal_signal and getattr(abnormal_signal, 'is_support_bounce', False):
            return "支撑反弹"

        if abnormal_signal and getattr(abnormal_signal, 'is_volume_breakout', False):
            return "放量转强"

        return "转强信号"

    def _calculate_signal_strength(
        self,
        cycle_judgement: ThemeCycleJudgement,
        abnormal_signal: Optional[StockAbnormalSignal],
        inputs: WeakToStrongDetectionInputs
    ) -> float:
        """计算信号强度"""
        strength = 50.0  # 基础分

        # 阶段转换加分
        prev_stage = getattr(cycle_judgement, 'prev_stage', '')
        current_stage = cycle_judgement.primary_cycle_stage.lower()

        if prev_stage in ["divergence", "decline"] and current_stage in ["rebound", "fermentation"]:
            strength += 20.0

        if "弱转强" in cycle_judgement.action_bias:
            strength += 15.0

        # 置信度加分
        confidence = cycle_judgement.confidence
        strength += min(confidence * 0.3, 15.0)

        # 异常信号加分
        if abnormal_signal:
            abnormal_score = getattr(abnormal_signal, 'abnormal_composite_score', 0)
            strength += min(abnormal_score * 0.2, 10.0)

        # 限制在0-100之间
        return min(max(strength, 0), 100)

    def _calculate_confidence_score(
        self,
        cycle_judgement: ThemeCycleJudgement,
        abnormal_signal: Optional[StockAbnormalSignal],
        inputs: WeakToStrongDetectionInputs
    ) -> float:
        """计算置信度分数"""
        confidence = 50.0  # 基础置信度

        # 周期置信度
        cycle_confidence = cycle_judgement.confidence
        confidence += min(cycle_confidence * 0.4, 20.0)

        # 异常信号确认
        if abnormal_signal and getattr(abnormal_signal, 'abnormal_composite_score', 0) > 60:
            confidence += 15.0

        # 量价配合
        if inputs.current_day_data:
            pct_chg = inputs.current_day_data.get('pct_chg', 0)
            volume_ratio = inputs.current_day_data.get('volume_ratio', 0)

            if pct_chg > 3 and volume_ratio > 1.5:
                confidence += 10.0

        return min(max(confidence, 0), 100)

    def _extract_volume_features(
        self,
        abnormal_signal: Optional[StockAbnormalSignal],
        inputs: WeakToStrongDetectionInputs
    ) -> Dict[str, Any]:
        """提取量价特征"""
        features = {
            'volume_ratio': 0.0,
            'turnover_rate': 0.0,
            'pct_chg': 0.0,
            'main_net_inflow': 0.0,
            'is_limit_up': False,
            'is_volume_breakout': False,
            'has_capital_inflow': False
        }

        if abnormal_signal:
            features['volume_ratio'] = getattr(abnormal_signal, 'volume_ratio_to_ma50', 0)
            features['turnover_rate'] = getattr(abnormal_signal, 'turnover_rate', 0)
            features['is_volume_breakout'] = getattr(abnormal_signal, 'is_volume_breakout', False)
            features['has_capital_inflow'] = getattr(abnormal_signal, 'has_hot_money_buy', False) or getattr(abnormal_signal, 'has_institution_buy', False)

        if inputs.current_day_data:
            features['pct_chg'] = inputs.current_day_data.get('pct_chg', 0)
            features['main_net_inflow'] = inputs.current_day_data.get('main_net_inflow', 0)
            features['is_limit_up'] = inputs.current_day_data.get('is_limit_up', False)

        return features

    async def _analyze_weak_to_strong_features(
        self,
        cycle_judgement: ThemeCycleJudgement,
        abnormal_signal: Optional[StockAbnormalSignal],
        inputs: WeakToStrongDetectionInputs
    ) -> Dict[str, Any]:
        """分析弱转强特征（基于PDF规则）"""
        features = {
            # 龙头和板块特征
            'is_dragon_head': False,
            'dragon_head_level': '',
            'has_plate_support': False,
            'plate_support_strength': 0.0,

            # 弱势类型
            'weak_type': '',
            'weak_intensity': 0.0,
            'weak_detailed_type': '',  # 更详细的弱势类型
            'is_bad_limit_up': False,  # 是否是烂板
            'bad_limit_up_score': 0.0,  # 烂板质量评分

            # 分时特征
            'intraday_pattern': '',
            'bid_weak_to_strong': False,
            'early_weak_to_strong': False,
            'intraday_weak_to_strong': False,
            'late_strength': False,  # 尾盘走强
            'intraday_signals': [],  # 分时信号列表

            # 反包特征
            'is_engulfing': False,
            'engulfing_strength': 0.0,
            'previous_close_pct': 0.0,

            # 核心原则
            'weak_not_weak_principle': False,  # "该弱不弱"原则
            'weak_not_weak_score': 0.0,  # 该弱不弱评分
        }

        # 提取股票ID和日期，用于数据库K线数据分析
        stock_id = getattr(cycle_judgement, 'stock_id', '')
        analysis_date = None

        # 从当前日数据中提取日期
        if inputs.current_day_data:
            current_date_str = inputs.current_day_data.get('trade_date')
            if current_date_str:
                try:
                    from datetime import datetime
                    analysis_date = datetime.strptime(current_date_str, '%Y-%m-%d').date()
                except:
                    pass

        # 1. 龙头识别：根据cycle_judgement判断是否龙头
        # 检查cycle_judgement中是否包含龙头判断字段
        if hasattr(cycle_judgement, 'is_dragon_head'):
            features['is_dragon_head'] = cycle_judgement.is_dragon_head
        elif hasattr(cycle_judgement, 'dragon_head_level'):
            features['dragon_head_level'] = cycle_judgement.dragon_head_level
            features['is_dragon_head'] = cycle_judgement.dragon_head_level in ['absolute', 'relative']
        # 如果没有明确字段，根据action_bias判断
        elif "龙头" in cycle_judgement.action_bias or "前排" in cycle_judgement.action_bias:
            features['is_dragon_head'] = True
            features['dragon_head_level'] = 'relative'

        # 2. 弱势类型：根据前一日数据判断（基于PDF详细分类）
        if inputs.prev_day_data:
            prev_open = inputs.prev_day_data.get('open', 0)
            prev_high = inputs.prev_day_data.get('high', 0)
            prev_low = inputs.prev_day_data.get('low', 0)
            prev_close = inputs.prev_day_data.get('close', 0)
            prev_pct_chg = inputs.prev_day_data.get('pct_chg', 0)
            prev_volume = inputs.prev_day_data.get('volume', 0)
            prev_upper_shadow_ratio = inputs.prev_day_data.get('upper_shadow_ratio', 0)
            prev_is_limit_up = inputs.prev_day_data.get('is_limit_up', False)
            prev_limit_up_open_count = inputs.prev_day_data.get('limit_up_open_count', 0)
            prev_is_bad_limit_up = inputs.prev_day_data.get('is_bad_limit_up', False)
            prev_limit_up_break_times = inputs.prev_day_data.get('limit_up_break_times', 0)
            prev_limit_up_recovery = inputs.prev_day_data.get('limit_up_recovery', True)  # 烂板后是否能收回

            # 计算上引线比例（如果未提供）
            if prev_upper_shadow_ratio <= 0 and prev_high > 0 and prev_close > 0:
                upper_shadow = prev_high - max(prev_open, prev_close)
                body_height = abs(prev_close - prev_open)
                if body_height > 0:
                    prev_upper_shadow_ratio = upper_shadow / body_height

            # 弱势类型判断（PDF中提到的3种常见弱势）
            # 2.1 中到大阴线：连板过程中T日出现中到大阴线（跌幅 > -3%）
            if prev_pct_chg < -3.0:
                features['weak_type'] = 'big_negative_line'
                features['weak_detailed_type'] = f'中到大阴线（跌幅{prev_pct_chg:.1f}%）'
                features['weak_intensity'] = min(abs(prev_pct_chg) / 10.0, 1.0)  # 标准化

            # 2.2 上引线：连板过程中T日出现冲高回落出现上引线（上引线比例 > 30%）
            elif prev_upper_shadow_ratio > 0.3:
                features['weak_type'] = 'upper_shadow'
                features['weak_detailed_type'] = f'上引线（比例{prev_upper_shadow_ratio:.1%}）'
                features['weak_intensity'] = prev_upper_shadow_ratio

            # 2.3 烂板（栏板）：连板过程中T日出现栏板涨停
            elif prev_is_limit_up and (prev_is_bad_limit_up or prev_limit_up_open_count > 2):
                features['weak_type'] = 'bad_limit_up'
                features['weak_detailed_type'] = f'烂板（开板{prev_limit_up_open_count}次）'
                features['is_bad_limit_up'] = True
                features['weak_intensity'] = min(prev_limit_up_open_count / 10.0, 1.0)

                # 烂板质量评分（基于PDF中的烂板5要素）
                bad_limit_up_score = 0.0
                bad_limit_up_factors = []

                # 要素1: 涨停位置 - 箱体突破位置，涨停板出现在前期高点位置
                # （需要历史数据，这里简化处理）
                if inputs.prev_day_data.get('is_breakout', False):
                    bad_limit_up_score += 0.3
                    bad_limit_up_factors.append("涨停位置在箱体突破位")

                # 要素2: 放量 - 把前期的套牢盘释放出来
                volume_ratio = inputs.prev_day_data.get('volume_ratio', 0)
                if volume_ratio > 1.5:
                    bad_limit_up_score += 0.2
                    bad_limit_up_factors.append(f"放量明显（量比{volume_ratio:.1f}）")

                # 要素3: 炸板 - 不破板就没有机会进入（已有开板次数）
                if prev_limit_up_open_count >= 2:
                    bad_limit_up_score += 0.2
                    bad_limit_up_factors.append(f"炸板{prev_limit_up_open_count}次，提供入场机会")

                # 要素4: 破板之后不能大跌，均线之上震荡，回撤幅度在3%之内
                max_drawdown = inputs.prev_day_data.get('max_drawdown_after_break', 0)
                if max_drawdown < 3.0:  # 回撤小于3%
                    bad_limit_up_score += 0.2
                    bad_limit_up_factors.append(f"破板后回撤小（{max_drawdown:.1f}%）")

                # 要素5: 烂板的封单量要比正常的封单量少，缩量走势
                closing_order_volume_ratio = inputs.prev_day_data.get('closing_order_volume_ratio', 1.0)
                if closing_order_volume_ratio < 0.8:  # 封单量比正常少
                    bad_limit_up_score += 0.1
                    bad_limit_up_factors.append("封单量减少，洗盘特征")

                features['bad_limit_up_score'] = bad_limit_up_score
                if bad_limit_up_factors:
                    features['bad_limit_up_factors'] = bad_limit_up_factors

                # 烂而不弱特征
                if bad_limit_up_score >= 0.6 and prev_limit_up_recovery:
                    features['weak_detailed_type'] += "（烂而不弱）"

        # 3. 分时弱转强分析（基于PDF详细描述）
        if inputs.current_day_data:
            intraday_data = inputs.current_day_data.get('intraday', {})
            current_pct_chg = inputs.current_day_data.get('pct_chg', 0)

            # 基础条件：当日上涨，且前一日有弱势特征
            if features.get('weak_type') and current_pct_chg > 0:
                # 3.1 集合竞价弱转强（高开或抢筹）
                bid_data = intraday_data.get('bid', {})
                if bid_data:
                    bid_open = bid_data.get('open', 0)
                    bid_close = bid_data.get('close', 0)
                    bid_volume_ratio = bid_data.get('volume_ratio', 0)

                    # 高开判断：竞价结束价 > 前一日收盘价
                    if inputs.prev_day_data and bid_close > 0:
                        prev_close = inputs.prev_day_data.get('close', 0)
                        if prev_close > 0 and bid_close > prev_close * 1.01:  # 高开1%以上
                            features['bid_weak_to_strong'] = True
                            features['intraday_signals'].append(f"集合竞价高开{(bid_close/prev_close-1)*100:.1f}%")

                            # 竞价量比放大
                            if bid_volume_ratio > 2.0:
                                features['intraday_signals'].append(f"竞价量比放大{bid_volume_ratio:.1f}倍，抢筹明显")

                    # 竞价走势：从低到高
                    if bid_open > 0 and bid_close > bid_open * 1.02:  # 竞价上涨2%以上
                        features['intraday_signals'].append("集合竞价从低到高，显示资金抢筹")

                # 3.2 早盘分时弱转强（PDF重点）
                early_data = intraday_data.get('early', {})
                if early_data:
                    early_prices = early_data.get('prices', [])
                    early_volumes = early_data.get('volumes', [])

                    if len(early_prices) >= 10:  # 至少有10个早盘数据点
                        early_start = early_prices[0] if early_prices else 0
                        early_end = early_prices[-1] if early_prices else 0

                        # 早盘不单边下跌，而是放量拉升
                        if early_end > early_start * 1.01:  # 早盘上涨1%以上
                            features['early_weak_to_strong'] = True
                            features['intraday_signals'].append("早盘放量拉升，分时弱转强")

                        # 分时均线之上运行（简化）
                        if len(early_prices) >= 30:
                            # 模拟分时均线（5分钟均线）
                            ma_prices = []
                            for i in range(5, len(early_prices)):
                                ma5 = sum(early_prices[i-5:i]) / 5
                                ma_prices.append(ma5)

                            # 检查是否从分时均线之下上升到之上（PDF关键信号）
                            if len(ma_prices) >= 10:
                                below_count = sum(1 for i in range(10) if early_prices[i+5] < ma_prices[i])
                                above_count = sum(1 for i in range(-5, 0) if early_prices[i+5] > ma_prices[i])
                                if below_count >= 7 and above_count >= 3:  # 明显从下到上转换
                                    features['intraday_signals'].append("分时从均线之下上升到均线之上，弱转强信号")

                # 3.3 盘中弱转强
                mid_data = intraday_data.get('mid', {})
                if mid_data:
                    # 盘中突然直线拉升（模拟）
                    mid_pattern = mid_data.get('pattern', '')
                    if 'sharp_rise' in mid_pattern:
                        features['intraday_weak_to_strong'] = True
                        features['intraday_signals'].append("盘中突然直线拉升，弱转强明显")

                # 3.4 尾盘走强（抢筹特征）
                late_data = intraday_data.get('late', {})
                if late_data:
                    late_prices = late_data.get('prices', [])
                    late_volumes = late_data.get('volumes', [])

                    if len(late_prices) >= 5:
                        late_start = late_prices[0] if late_prices else 0
                        late_end = late_prices[-1] if late_prices else 0

                        if late_end > late_start * 1.02:  # 尾盘拉升2%以上
                            features['late_strength'] = True
                            features['intraday_signals'].append("尾盘拉升，抢筹特征明显")

            # 设置分时模式描述
            if features['bid_weak_to_strong'] or features['early_weak_to_strong'] or features['intraday_weak_to_strong']:
                pattern_parts = []
                if features['bid_weak_to_strong']:
                    pattern_parts.append("集合竞价")
                if features['early_weak_to_strong']:
                    pattern_parts.append("早盘分时")
                if features['intraday_weak_to_strong']:
                    pattern_parts.append("盘中")
                if features['late_strength']:
                    pattern_parts.append("尾盘抢筹")

                if pattern_parts:
                    features['intraday_pattern'] = "+".join(pattern_parts) + "弱转强"

        # 4. 反包特征：判断是否反包前一日阴线
        if inputs.prev_day_data and inputs.current_day_data:
            prev_close = inputs.prev_day_data.get('close', 0)
            prev_high = inputs.prev_day_data.get('high', 0)
            current_close = inputs.current_day_data.get('close', 0)
            current_high = inputs.current_day_data.get('high', 0)

            if prev_close > 0 and current_close > 0:
                # 反包：当日收盘价高于前一日最高价
                if current_close > prev_high:
                    features['is_engulfing'] = True
                    features['engulfing_strength'] = (current_close - prev_high) / prev_high * 100

                # 前一日涨跌幅
                features['previous_close_pct'] = prev_pct_chg if 'prev_pct_chg' in locals() else 0

        # 5. 支撑位和缺口分析（K线技术形态）
        if inputs.prev_day_data and inputs.current_day_data:
            support_analysis = await self._analyze_support_and_gaps(
                inputs.prev_day_data,
                inputs.current_day_data,
                historical_data=None,  # 暂时不传递历史数据
                stock_id=stock_id,
                analysis_date=analysis_date
            )
            # 将支撑位分析结果合并到features
            if support_analysis['has_support']:
                features['has_support'] = True
                features['support_type'] = support_analysis['support_type']
                features['support_strength'] = support_analysis['support_strength']
                features['support_level'] = support_analysis['support_level']
                features['is_gap_support'] = support_analysis['is_gap_support']
            # 将技术信号添加到证据中
            if support_analysis['technical_signals']:
                features.setdefault('technical_evidence', []).extend(support_analysis['technical_signals'])

        # 6. 板块支持：检查是否有板块联动
        if inputs.theme_environment:
            plate_strength = inputs.theme_environment.get('plate_strength', 0)
            features['has_plate_support'] = plate_strength > 50
            features['plate_support_strength'] = plate_strength

        # 7. "该弱不弱"核心原则检测（PDF核心）
        # 原则：看似走弱，但实际上有资金护盘，第二天强势反包
        if inputs.prev_day_data and inputs.current_day_data:
            prev_pct_chg = inputs.prev_day_data.get('pct_chg', 0)
            current_pct_chg = inputs.current_day_data.get('pct_chg', 0)
            prev_close = inputs.prev_day_data.get('close', 0)
            current_close = inputs.current_day_data.get('close', 0)

            weak_not_weak_score = 0.0
            weak_not_weak_factors = []

            # 条件1：前一日有弱势特征（已检测）
            if features.get('weak_type'):
                weak_not_weak_score += 0.3
                weak_not_weak_factors.append(f"前一日出现{features.get('weak_detailed_type', '弱势')}")

            # 条件2：当日强势反包或上涨
            if current_pct_chg > abs(prev_pct_chg) * 0.8:  # 当日涨幅超过前一日跌幅的80%
                weak_not_weak_score += 0.3
                weak_not_weak_factors.append(f"当日上涨{current_pct_chg:.1f}%，反包前一日跌幅")

            # 条件3：支撑位有效
            if features.get('has_support'):
                weak_not_weak_score += 0.2
                weak_not_weak_factors.append(f"在{features.get('support_type')}获得支撑")

            # 条件4：成交量配合
            if inputs.prev_day_data and inputs.current_day_data:
                prev_volume = inputs.prev_day_data.get('volume', 0)
                current_volume = inputs.current_day_data.get('volume', 0)
                if current_volume > prev_volume * 0.8:  # 成交量不低于前一日80%
                    weak_not_weak_score += 0.1
                    weak_not_weak_factors.append("成交量配合")

            # 条件5：资金流入（如果可用）
            if inputs.current_day_data.get('main_net_inflow', 0) > 0:
                weak_not_weak_score += 0.1
                weak_not_weak_factors.append("资金净流入")

            features['weak_not_weak_score'] = weak_not_weak_score
            if weak_not_weak_factors:
                features['weak_not_weak_factors'] = weak_not_weak_factors

            # 综合判断：该弱不弱原则成立
            if weak_not_weak_score >= 0.6:
                features['weak_not_weak_principle'] = True
                # 添加到技术证据
                if 'technical_evidence' not in features:
                    features['technical_evidence'] = []
                features['technical_evidence'].append(f"'该弱不弱'原则成立（评分{weak_not_weak_score:.1f}/1.0）")

        return features

    async def _analyze_support_and_gaps(
        self,
        prev_day_data: Dict[str, Any],
        current_day_data: Dict[str, Any],
        historical_data: List[Dict[str, Any]] = None,
        stock_id: str = None,
        analysis_date: date = None
    ) -> Dict[str, Any]:
        """
        分析支撑位和缺口（基于K线技术形态）

        弱转强买入法重要环节：前一日下跌到短期支撑位，比如缺口位置

        Args:
            prev_day_data: 前一日K线数据
            current_day_data: 当日K线数据
            historical_data: 历史K线数据（可选）

        Returns:
            包含支撑位和缺口分析结果的字典
        """
        analysis = {
            'has_support': False,
            'support_level': 0.0,
            'support_type': '',  # 'gap', 'ma', 'fibonacci', 'previous_low', 'gap_support'
            'support_strength': 0.0,
            'has_gap': False,
            'gap_type': '',  # 'breakaway', 'runaway', 'exhaustion', 'common'
            'gap_position': '',  # 'above', 'below'
            'gap_size': 0.0,
            'is_gap_support': False,
            'gap_support_level': 0.0,
            'gap_support_strength': 0.0,
            'technical_signals': [],
            'intraday_signals': []  # 分时特征信号
        }

        if not prev_day_data or not current_day_data:
            return analysis

        # 如果提供了股票ID和分析日期，并且有K线数据服务，尝试从数据库获取真实分析
        if stock_id and analysis_date and self.kline_data_service:
            try:
                # 使用KlineDataService进行缺口支撑分析
                gap_support_analysis = await self.kline_data_service.analyze_gap_support(
                    stock_id, analysis_date
                )
                # 将KlineDataService的分析结果转换为当前格式
                if gap_support_analysis:
                    analysis.update({
                        'has_gap': gap_support_analysis.get('has_gap', False),
                        'gap_type': gap_support_analysis.get('gap_type', ''),
                        'gap_position': gap_support_analysis.get('gap_position', ''),
                        'gap_size': gap_support_analysis.get('gap_size', 0.0),
                        'has_support': gap_support_analysis.get('has_support', False),
                        'support_type': gap_support_analysis.get('support_type', ''),
                        'support_strength': gap_support_analysis.get('support_strength', 0.0),
                        'is_gap_support': gap_support_analysis.get('is_gap_support', False),
                        'gap_support_level': gap_support_analysis.get('gap_support_level', 0.0),
                        'technical_signals': gap_support_analysis.get('technical_signals', [])
                    })
                    # 返回数据库分析结果，不再执行后续模拟分析
                    return analysis
            except Exception as e:
                logger.warning(f"使用KlineDataService分析股票{stock_id}缺口支撑失败: {e}")
                # 继续使用模拟数据进行分析

        try:
            # 提取价格数据
            prev_open = prev_day_data.get('open', 0)
            prev_high = prev_day_data.get('high', 0)
            prev_low = prev_day_data.get('low', 0)
            prev_close = prev_day_data.get('close', 0)
            prev_volume = prev_day_data.get('volume', 0)
            prev_pct_chg = prev_day_data.get('pct_chg', 0)

            current_open = current_day_data.get('open', 0)
            current_high = current_day_data.get('high', 0)
            current_low = current_day_data.get('low', 0)
            current_close = current_day_data.get('close', 0)
            current_volume = current_day_data.get('volume', 0)
            current_pct_chg = current_day_data.get('pct_chg', 0)

            if prev_open <= 0 or current_open <= 0:
                return analysis

            # 0. 分时数据提取（用于分时弱转强分析）
            intraday_data = current_day_data.get('intraday', {})
            bid_data = intraday_data.get('bid', {})  # 集合竞价数据
            early_data = intraday_data.get('early', {})  # 早盘数据
            intraday_prices = intraday_data.get('prices', [])  # 分时价格序列
            intraday_volumes = intraday_data.get('volumes', [])  # 分时成交量序列

            # 1. 缺口分析（根据PDF增强）
            # 向上缺口：当日最低价 > 前一日最高价（强缺口）
            # 普通向上缺口：当日开盘价 > 前一日最高价
            # 向下缺口：当日最高价 < 前一日最低价
            # 普通向下缺口：当日开盘价 < 前一日最低价

            gap_threshold = 0.001  # 缺口阈值0.1%

            # 强向上缺口
            if current_low > prev_high * (1 + gap_threshold):
                analysis['has_gap'] = True
                analysis['gap_type'] = 'breakaway'  # 突破缺口
                analysis['gap_position'] = 'above'
                analysis['gap_size'] = (current_low - prev_high) / prev_high * 100
                analysis['technical_signals'].append(f"向上突破缺口: {analysis['gap_size']:.2f}%")
            # 普通向上缺口
            elif current_open > prev_high * (1 + gap_threshold):
                analysis['has_gap'] = True
                analysis['gap_type'] = 'common'
                analysis['gap_position'] = 'above'
                analysis['gap_size'] = (current_open - prev_high) / prev_high * 100
                analysis['technical_signals'].append(f"向上普通缺口: {analysis['gap_size']:.2f}%")
            # 强向下缺口
            elif current_high < prev_low * (1 - gap_threshold):
                analysis['has_gap'] = True
                analysis['gap_type'] = 'breakaway'
                analysis['gap_position'] = 'below'
                analysis['gap_size'] = (prev_low - current_high) / prev_low * 100
                analysis['technical_signals'].append(f"向下突破缺口: {analysis['gap_size']:.2f}%")
            # 普通向下缺口
            elif current_open < prev_low * (1 - gap_threshold):
                analysis['has_gap'] = True
                analysis['gap_type'] = 'common'
                analysis['gap_position'] = 'below'
                analysis['gap_size'] = (prev_low - current_open) / prev_low * 100
                analysis['technical_signals'].append(f"向下普通缺口: {analysis['gap_size']:.2f}%")

            # 2. 支撑位分析（根据PDF增强）
            support_levels = []

            # 2.1 前一日低点支撑（基础支撑）
            if prev_low > 0:
                support_levels.append({
                    'level': prev_low,
                    'type': 'previous_low',
                    'strength': 0.6,
                    'description': '前一日低点'
                })

            # 2.2 缺口支撑（向上缺口的缺口下沿）
            if analysis['has_gap'] and analysis['gap_position'] == 'above':
                gap_support = prev_high
                gap_support_strength = 0.8  # 缺口支撑较强
                support_levels.append({
                    'level': gap_support,
                    'type': 'gap_support',
                    'strength': gap_support_strength,
                    'description': f'缺口支撑（缺口下沿）'
                })

                # 检查缺口支撑是否有效（价格在缺口支撑附近）
                if current_low >= gap_support * 0.99 and current_low <= gap_support * 1.01:
                    analysis['is_gap_support'] = True
                    analysis['gap_support_level'] = gap_support
                    analysis['gap_support_strength'] = gap_support_strength
                    analysis['technical_signals'].append(f"缺口支撑有效: {gap_support:.2f}（回补缺口）")

                    # 缺口回补特征：价格回到缺口下沿并反弹
                    if current_close > gap_support and prev_pct_chg < 0:
                        analysis['technical_signals'].append("缺口回补后反弹，形成弱转强")

            # 2.3 前一日收盘价支撑（如果收盘价在K线实体中部或以上）
            if prev_close > 0:
                # 如果前一日是阴线，但收盘价在实体上半部分
                if prev_close < prev_open:  # 阴线
                    body_mid = (prev_open + prev_close) / 2
                    if prev_close > body_mid:  # 收盘在实体上半部分
                        support_levels.append({
                            'level': prev_close,
                            'type': 'previous_close',
                            'strength': 0.5,
                            'description': '前一日收盘价支撑'
                        })

            # 2.4 关键价格位支撑（整数关口、前高前低等）
            # 检查整数关口支撑（如10.00、10.50等）
            integer_levels = []
            base_levels = [1.00, 2.00, 5.00, 10.00, 20.00, 50.00]
            for base in base_levels:
                for multiplier in [0.5, 1.0, 1.5, 2.0]:
                    level = base * multiplier
                    if prev_low > 0 and abs(prev_low - level) / level < 0.02:  # 2%以内
                        integer_levels.append(level)

            for level in integer_levels[:2]:  # 最多取两个关键整数位
                support_levels.append({
                    'level': level,
                    'type': 'integer_level',
                    'strength': 0.4,
                    'description': f'整数关口支撑 {level:.2f}'
                })

            # 3. 寻找最强支撑位
            if support_levels:
                # 按支撑强度排序
                support_levels.sort(key=lambda x: x['strength'], reverse=True)
                strongest = support_levels[0]

                # 检查是否在当前价格附近获得支撑
                support_distance_pct = abs(current_low - strongest['level']) / strongest['level'] * 100
                support_threshold = 2.0  # 2%以内认为是支撑有效

                if support_distance_pct < support_threshold:
                    analysis['has_support'] = True
                    analysis['support_level'] = strongest['level']
                    analysis['support_type'] = strongest['type']
                    analysis['support_strength'] = strongest['strength']

                    signal_desc = f"在{strongest['description']}{strongest['level']:.2f}获得支撑"
                    if prev_pct_chg < -2.0:  # 前一日跌幅较大
                        signal_desc += f"（前一日下跌{prev_pct_chg:.1f}%后获得支撑）"
                    analysis['technical_signals'].append(signal_desc)

                    # 特别标注缺口支撑
                    if strongest['type'] == 'gap_support' and analysis['is_gap_support']:
                        analysis['technical_signals'].append(f"缺口支撑验证通过：价格在缺口下沿{strongest['level']:.2f}获得强支撑")

            # 4. 分时弱转强特征分析（基于PDF）
            # 4.1 集合竞价弱转强（高开或抢筹）
            if bid_data:
                bid_open = bid_data.get('open', 0)
                bid_close = bid_data.get('close', 0)  # 集合竞价结束价
                bid_volume_ratio = bid_data.get('volume_ratio', 0)  # 竞价量比

                # 高开：竞价结束价 > 前一日收盘价
                if bid_close > prev_close * 1.01:  # 高开1%以上
                    analysis['intraday_signals'].append("集合竞价高开，显示弱转强")
                    # 竞价量比放大
                    if bid_volume_ratio > 2.0:
                        analysis['intraday_signals'].append(f"集合竞价量比放大{bid_volume_ratio:.1f}倍，抢筹明显")

                # 竞价走势：从低到高
                if bid_open > 0 and bid_close > bid_open * 1.02:  # 竞价上涨2%以上
                    analysis['intraday_signals'].append("集合竞价从低到高，显示资金抢筹")

            # 4.2 早盘分时弱转强
            if early_data and len(intraday_prices) >= 30:  # 至少有30分钟数据
                # 早盘前30分钟走势分析
                early_prices = intraday_prices[:30] if len(intraday_prices) >= 30 else intraday_prices
                early_volumes = intraday_volumes[:30] if len(intraday_volumes) >= 30 else intraday_volumes

                if early_prices:
                    early_min = min(early_prices)
                    early_max = max(early_prices)
                    early_open = early_prices[0] if early_prices else 0
                    early_close = early_prices[-1] if early_prices else 0

                    # 早盘不单边下跌，而是放量拉升
                    if early_close > early_open and current_pct_chg > 0:
                        # 计算早盘成交量
                        if early_volumes:
                            early_avg_volume = sum(early_volumes) / len(early_volumes)
                            # 简单判断放量
                            if len(early_volumes) > 10 and early_volumes[-1] > early_avg_volume * 1.5:
                                analysis['intraday_signals'].append("早盘放量拉升，分时弱转强")

                    # 分时均线之上运行（简化模拟）
                    if len(intraday_prices) >= 60:  # 有60分钟数据
                        ma_prices = []
                        for i in range(30, len(intraday_prices)):
                            if i >= 5:  # 5分钟均线
                                ma5 = sum(intraday_prices[i-5:i]) / 5
                                ma_prices.append(ma5)

                        # 检查是否从分时均线之下上升到之上
                        if len(ma_prices) >= 10:
                            below_count = sum(1 for i in range(10) if intraday_prices[30+i] < ma_prices[i])
                            above_count = sum(1 for i in range(-10, 0) if intraday_prices[i] > ma_prices[i])
                            if below_count >= 6 and above_count >= 6:  # 从下到上转换
                                analysis['intraday_signals'].append("分时从均线之下上升到均线之上，弱转强信号")

            # 4.3 尾盘抢筹特征
            if len(intraday_prices) >= 60:  # 有全天数据
                last_30_prices = intraday_prices[-30:] if len(intraday_prices) >= 30 else intraday_prices
                last_30_volumes = intraday_volumes[-30:] if len(intraday_volumes) >= 30 else intraday_volumes

                if last_30_prices and last_30_volumes:
                    last_price = last_30_prices[-1] if last_30_prices else 0
                    last_10_avg = sum(last_30_prices[-10:]) / 10 if len(last_30_prices) >= 10 else 0
                    last_volume_avg = sum(last_30_volumes[-10:]) / 10 if len(last_30_volumes) >= 10 else 0

                    # 尾盘拉升：最后价格高于尾盘均价
                    if last_price > last_10_avg * 1.01 and last_30_volumes[-1] > last_volume_avg * 1.5:
                        analysis['intraday_signals'].append("尾盘放量拉升，抢筹特征明显")

            # 5. 使用TA-Lib进行更高级的技术分析（如果可用）
            if TA_LIB_AVAILABLE and historical_data and len(historical_data) >= 20:
                # 提取OHLC数据
                closes = [d.get('close', 0) for d in historical_data if d.get('close', 0) > 0]
                highs = [d.get('high', 0) for d in historical_data if d.get('high', 0) > 0]
                lows = [d.get('low', 0) for d in historical_data if d.get('low', 0) > 0]

                if len(closes) >= 20:
                    # 计算移动平均线作为动态支撑
                    ma5 = talib.SMA(np.array(closes), timeperiod=5)[-1] if len(closes) >= 5 else 0
                    ma10 = talib.SMA(np.array(closes), timeperiod=10)[-1] if len(closes) >= 10 else 0
                    ma20 = talib.SMA(np.array(closes), timeperiod=20)[-1] if len(closes) >= 20 else 0

                    # 检查是否在移动平均线附近
                    for ma_value, ma_period in [(ma5, 5), (ma10, 10), (ma20, 20)]:
                        if ma_value > 0:
                            distance = abs(current_low - ma_value) / ma_value * 100
                            if distance < 1.5:  # 距离MA 1.5%以内
                                # 避免重复设置支撑位
                                if not analysis['has_support'] or analysis['support_strength'] < 0.7:
                                    analysis['has_support'] = True
                                    analysis['support_level'] = ma_value
                                    analysis['support_type'] = f'ma{ma_period}'
                                    analysis['support_strength'] = 0.7
                                    analysis['technical_signals'].append(f"在{ma_period}日均线{ma_value:.2f}获得支撑")
                                break

        except Exception as e:
            logger.error(f"支撑位和缺口分析失败: {e}")

        return analysis

    def _collect_evidence(
        self,
        cycle_judgement: ThemeCycleJudgement,
        abnormal_signal: Optional[StockAbnormalSignal],
        inputs: WeakToStrongDetectionInputs
    ) -> List[str]:
        """收集证据"""
        evidence = []

        # 阶段转换证据
        prev_stage = getattr(cycle_judgement, 'prev_stage', '')
        current_stage = cycle_judgement.primary_cycle_stage

        if prev_stage and current_stage:
            evidence.append(f"周期阶段从{prev_stage}转为{current_stage}")

        if "弱转强" in cycle_judgement.action_bias:
            evidence.append("操作偏向明确提示弱转强")

        # 量价证据
        if abnormal_signal:
            if getattr(abnormal_signal, 'is_volume_breakout', False):
                evidence.append("成交量出现突破信号")

            if getattr(abnormal_signal, 'has_hot_money_buy', False):
                evidence.append("有活跃资金买入")

            if getattr(abnormal_signal, 'has_institution_buy', False):
                evidence.append("有机构资金参与")

        return evidence

    def _generate_conclusion(self, signal_type: str, signal_strength: float) -> str:
        """生成结论"""
        if signal_strength >= 80:
            strength_desc = "强烈"
        elif signal_strength >= 60:
            strength_desc = "明显"
        else:
            strength_desc = "初步"

        return f"{strength_desc}{signal_type}信号，建议关注"

    def _assess_risk_level(self, signal_strength: float, confidence_score: float) -> str:
        """评估风险等级"""
        if signal_strength >= 70 and confidence_score >= 70:
            return "low"
        elif signal_strength >= 50 and confidence_score >= 50:
            return "medium"
        else:
            return "high"

    async def generate_weak_to_strong_judgement(
        self,
        signals: List[WeakToStrongSignal],
        market_state: Dict[str, Any]
    ) -> List[WeakToStrongJudgement]:
        """
        生成弱转强判断结果

        Args:
            signals: 弱转强信号列表
            market_state: 市场状态

        Returns:
            弱转强判断结果列表
        """
        judgements = []

        for signal in signals:
            judgement = await self._build_weak_to_strong_judgement(signal, market_state)
            if judgement:
                judgements.append(judgement)

        return judgements

    async def _build_weak_to_strong_judgement(
        self,
        signal: WeakToStrongSignal,
        market_state: Dict[str, Any]
    ) -> Optional[WeakToStrongJudgement]:
        """构建弱转强判断结果"""
        try:
            # 计算综合评分
            composite_score = self._calculate_composite_score(signal, market_state)

            # 确定操作建议
            action_bias, position_suggestion = self._determine_action(
                composite_score, signal, market_state
            )

            # 构建判断结果
            judgement = WeakToStrongJudgement(
                trade_date=signal.trade_date,
                stock_id=signal.stock_id,
                stock_name=signal.stock_name,
                subject_key=signal.subject_key,
                theme_name=signal.theme_name,
                weak_to_strong_score=composite_score,
                eligibility_score=composite_score * 0.8,  # 资格评分略低
                timing_score=self._calculate_timing_score(signal, market_state),
                primary_signal_type=signal.signal_type,
                supporting_signals=self._extract_supporting_signals(signal),
                action_bias=action_bias,
                position_suggestion=position_suggestion,
                stop_loss_level=self._calculate_stop_loss_level(signal),
                signal_analysis=self._generate_signal_analysis(signal),
                risk_assessment=self._generate_risk_assessment(signal),
                watch_points=self._generate_watch_points(signal),
                evidence=signal.evidence,
                conclusion=self._generate_judgement_conclusion(signal, composite_score, action_bias)
            )

            return judgement

        except Exception as e:
            logger.error(f"构建弱转强判断失败: {e}")
            return None

    def _calculate_composite_score(self, signal: WeakToStrongSignal, market_state: Dict[str, Any]) -> float:
        """计算综合评分"""
        # 基础分 = 信号强度 * 置信度 / 100
        base_score = (signal.signal_strength * signal.confidence_score) / 100

        # 市场状态调整
        market_mode = market_state.get('mode', 'standby')
        market_adjustment = {
            'offensive': 1.2,
            'defensive': 1.0,
            'cautious': 0.8,
            'standby': 0.5
        }.get(market_mode, 0.5)

        # 风险等级调整
        risk_adjustment = {
            'low': 1.1,
            'medium': 1.0,
            'high': 0.7
        }.get(signal.risk_level, 0.7)

        composite = base_score * market_adjustment * risk_adjustment
        return min(max(composite, 0), 100)

    def _calculate_timing_score(self, signal: WeakToStrongSignal, market_state: Dict[str, Any]) -> float:
        """计算时机评分"""
        timing = 50.0

        # 信号类型加分
        if signal.signal_type in ["分歧回流", "弱转强"]:
            timing += 20.0

        # 量价配合加分
        if signal.is_volume_breakout and signal.pct_chg > 0:
            timing += 15.0

        # 资金流入加分
        if signal.has_capital_inflow:
            timing += 10.0

        # 市场状态调整
        market_mode = market_state.get('mode', 'standby')
        if market_mode == 'offensive':
            timing += 10.0
        elif market_mode == 'standby':
            timing -= 20.0

        return min(max(timing, 0), 100)

    def _determine_action(
        self,
        composite_score: float,
        signal: WeakToStrongSignal,
        market_state: Dict[str, Any]
    ) -> Tuple[str, float]:
        """确定操作建议"""
        market_mode = market_state.get('mode', 'standby')
        position_limit = market_state.get('position_limit', 0.0)

        if composite_score >= 80 and market_mode in ['offensive', 'defensive']:
            action = "重点买入"
            position = min(0.3, position_limit * 0.6)  # 最多30%仓位
        elif composite_score >= 70 and market_mode in ['offensive', 'defensive', 'cautious']:
            action = "试错买入"
            position = min(0.15, position_limit * 0.4)  # 最多15%仓位
        elif composite_score >= 60:
            action = "观察"
            position = 0.0
        else:
            action = "回避"
            position = 0.0

        return action, position

    def _calculate_stop_loss_level(self, signal: WeakToStrongSignal) -> float:
        """计算止损位"""
        # 根据风险等级确定止损位
        risk_stop_loss = {
            'low': -5.0,   # 低风险：-5%
            'medium': -7.0, # 中等风险：-7%
            'high': -10.0  # 高风险：-10%
        }.get(signal.risk_level, -8.0)

        return risk_stop_loss

    def _extract_supporting_signals(self, signal: WeakToStrongSignal) -> List[str]:
        """提取支撑信号"""
        supporting = []

        if signal.is_divergence_rebound:
            supporting.append("分歧回流")

        if signal.is_support_bounce:
            supporting.append("支撑反弹")

        if signal.is_volume_breakout:
            supporting.append("放量突破")

        if signal.has_capital_inflow:
            supporting.append("资金流入")

        if signal.is_limit_up:
            supporting.append("涨停确认")

        return supporting

    def _generate_signal_analysis(self, signal: WeakToStrongSignal) -> str:
        """生成信号分析"""
        analysis = f"{signal.signal_type}信号，强度{signal.signal_strength:.1f}，置信度{signal.confidence_score:.1f}"

        if signal.is_divergence_rebound:
            analysis += "。经历分歧后资金回流，情绪转暖"

        if signal.is_volume_breakout:
            analysis += "。成交量放大配合价格上涨"

        if signal.has_capital_inflow:
            analysis += "。有主动资金流入推动"

        return analysis

    def _generate_risk_assessment(self, signal: WeakToStrongSignal) -> str:
        """生成风险评估"""
        risk_desc = {
            'low': "低风险",
            'medium': "中等风险",
            'high': "高风险"
        }.get(signal.risk_level, "未知风险")

        return f"{risk_desc}。信号质量{signal.signal_strength:.1f}，需要关注市场整体环境和板块轮动"

    def _generate_watch_points(self, signal: WeakToStrongSignal) -> List[str]:
        """生成关注要点"""
        watch_points = []

        if signal.is_divergence_rebound:
            watch_points.append("观察回流持续性，避免假突破")

        if signal.is_volume_breakout:
            watch_points.append("关注成交量能否持续放大")

        if signal.pct_chg > 5:
            watch_points.append("涨幅较大，注意获利盘压力")

        watch_points.append("设置止损位，控制风险")

        return watch_points

    def _generate_judgement_conclusion(
        self,
        signal: WeakToStrongSignal,
        composite_score: float,
        action_bias: str
    ) -> str:
        """生成判断结论"""
        if composite_score >= 80:
            conclusion = f"强{signal.signal_type}信号，{action_bias}"
        elif composite_score >= 70:
            conclusion = f"中等{signal.signal_type}信号，{action_bias}"
        elif composite_score >= 60:
            conclusion = f"初步{signal.signal_type}信号，{action_bias}"
        else:
            conclusion = f"{signal.signal_type}信号较弱，{action_bias}"

        return conclusion


# 示例用法
async def example_usage():
    """示例用法"""
    service = WeakToStrongService()

    # 模拟输入数据
    inputs = WeakToStrongDetectionInputs(
        cycle_judgement=ThemeCycleJudgement(
            trade_date="2026-04-10",
            subject_key="AI芯片",
            theme_name="人工智能芯片国产替代",
            is_main_theme=True,
            is_divergence=True,
            is_rebound=True,
            primary_cycle_stage="rebound",
            action_bias="弱转强",
            confidence=75.0,
            conclusion="分歧后回流，弱转强信号"
        ),
        abnormal_signal=None,
        market_environment={"mode": "offensive", "position_limit": 1.0}
    )

    trade_date = date(2026, 4, 10)
    signals = await service.detect_weak_to_strong_signals(trade_date, inputs)

    if signals:
        market_state = {"mode": "offensive", "position_limit": 1.0}
        judgements = await service.generate_weak_to_strong_judgement(signals, market_state)

        for judgement in judgements:
            print(f"股票: {judgement.stock_name}")
            print(f"弱转强评分: {judgement.weak_to_strong_score:.1f}")
            print(f"操作建议: {judgement.action_bias}")
            print(f"仓位建议: {judgement.position_suggestion:.1%}")
            print(f"结论: {judgement.conclusion}")
            print()


if __name__ == "__main__":
    asyncio.run(example_usage())
