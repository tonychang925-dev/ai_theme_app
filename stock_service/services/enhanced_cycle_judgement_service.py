from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple
from datetime import date

from stock_service.services.cycle_judgement_service import (
    CycleJudgementService,
    ThemeCycleMainlineInput,
    ThemeCycleMarketInput,
    ThemeCycleRecentInput,
)
from stock_service.models import ThemeCycleJudgement


@dataclass(frozen=True)
class PreviousCycleState:
    """前一日周期状态"""
    subject_key: str
    trade_date: date
    cycle_state: str
    mainline_alive: bool
    fade_watch: bool = False
    fade_confirmed: bool = False


class ThemeCycleStateMachine:
    """
    主题周期状态机
    管理状态转换逻辑
    """

    # 允许的状态转换
    TRANSITION_RULES = {
        # 正常演进路径
        "start": ["fermentation", "fade"],
        "fermentation": ["acceleration", "divergence", "fade_watch"],
        "acceleration": ["divergence", "climax", "fade_watch"],
        "divergence": ["repair", "fade_watch", "fade_confirmed"],
        "repair": ["fermentation", "divergence", "fade_watch"],
        "climax": ["divergence", "fade_watch", "fade_confirmed"],

        # 退潮相关状态
        "fade_watch": ["repair", "fade_confirmed", "fade"],
        "fade_confirmed": ["fade", "repair"],
        "fade": ["repair", "start"],
    }

    # 状态转换条件阈值
    THRESHOLDS = {
        "repair_to_fermentation": {
            "mainline_strength": 70,
            "leader_alive": 50,
            "event_count_3d": 2,
        },
        "fade_to_watch": {
            "mainline_strength": 40,
            "leader_alive": 30,
            "red_ratio": 0.3,
        },
        "watch_to_confirmed": {
            "mainline_strength": 30,
            "leader_alive": 20,
            "red_ratio": 0.2,
            "consecutive_days": 2,
        },
    }

    def transition(self, previous_state: Optional[PreviousCycleState],
                  current_raw_state: str,
                  market_inputs: ThemeCycleMarketInput,
                  strength_score: float = 50.0) -> Tuple[str, str, str]:
        """
        执行状态转换
        返回：(最终状态, 退潮状态细分, 转换原因)
        """
        if previous_state is None:
            # 无历史状态，使用原始状态
            fade_status = self._determine_fade_status(current_raw_state, None)
            return current_raw_state, fade_status, "初始状态"

        previous = previous_state.cycle_state

        # 检查是否允许转换
        if previous in self.TRANSITION_RULES and current_raw_state in self.TRANSITION_RULES[previous]:
            # 允许转换，应用细化规则
            final_state, fade_status, reason = self._apply_refined_rules(
                previous, current_raw_state, market_inputs, strength_score, previous_state
            )
        else:
            # 不允许的转换，保持原状态或特殊处理
            final_state, fade_status, reason = self._handle_invalid_transition(
                previous, current_raw_state, market_inputs, previous_state
            )

        return final_state, fade_status, reason

    def _determine_fade_status(self, current_state: str,
                              previous_state: Optional[PreviousCycleState]) -> str:
        """确定退潮状态细分"""
        if current_state == "fade":
            if previous_state is None:
                return "fade_watch"

            if previous_state.fade_confirmed:
                return "fade_confirmed"
            elif previous_state.fade_watch:
                return "fade_confirmed"
            elif previous_state.cycle_state in ["divergence", "rebound"]:
                return "fade_watch"
            else:
                return "fade_watch"

        return "none"

    def _apply_refined_rules(self, previous: str, current: str,
                            market: ThemeCycleMarketInput,
                            strength_score: float,
                            prev_state: PreviousCycleState) -> Tuple[str, str, str]:
        """应用细化转换规则"""

        # 退潮相关状态转换
        if current == "fade":
            fade_status = self._determine_fade_status(current, prev_state)

            # 检查是否满足退潮观察条件
            if fade_status == "fade_watch":
                if (strength_score >= self.THRESHOLDS["fade_to_watch"]["mainline_strength"] and
                    market.limit_up_count > 0):
                    return "fade_watch", "fade_watch", "主线强度尚可，进入退潮观察"
                else:
                    return "fade", "fade_watch", "主线强度不足，直接退潮"

            # 退潮确认
            elif fade_status == "fade_confirmed":
                if prev_state.fade_watch:
                    # 检查是否满足确认条件
                    if (strength_score <= self.THRESHOLDS["watch_to_confirmed"]["mainline_strength"] and
                        market.limit_up_count == 0):
                        return "fade", "fade_confirmed", "主线强度持续不足，退潮确认"
                    else:
                        return "fade_watch", "fade_watch", "强度有修复，保持观察"
                else:
                    return "fade", "fade_confirmed", "跳过观察直接确认"

        # 修复到发酵的特殊转换
        if previous == "repair" and current == "fermentation":
            if (strength_score >= self.THRESHOLDS["repair_to_fermentation"]["mainline_strength"] and
                market.limit_up_count >= 2):
                return "fermentation", "none", "修复成功，回归发酵"
            else:
                return "repair", "none", "修复条件不足，保持修复状态"

        # 其他状态直接接受
        fade_status = self._determine_fade_status(current, prev_state)
        return current, fade_status, "正常状态转换"

    def _handle_invalid_transition(self, previous: str, current: str,
                                  market: ThemeCycleMarketInput,
                                  prev_state: PreviousCycleState) -> Tuple[str, str, str]:
        """处理无效状态转换"""
        # 如果从非退潮状态跳转到fade_confirmed，改为fade_watch
        if current == "fade_confirmed" and previous not in ["fade_watch", "fade"]:
            return "fade_watch", "fade_watch", "无效跳转：非退潮→确认，改为观察"

        # 如果从fade跳转到fermentation，检查条件
        if previous == "fade" and current == "fermentation":
            if market.limit_up_count >= 3:
                return "start", "none", "退潮后重新启动"
            else:
                return "fade", self._determine_fade_status("fade", prev_state), "退潮后条件不足"

        # 默认保持原状态
        fade_status = self._determine_fade_status(previous, prev_state)
        return previous, fade_status, f"无效转换：{previous}→{current}，保持原状态"


class EnhancedCycleJudgementService(CycleJudgementService):
    """
    增强版周期判定服务
    在原有基础上添加状态机追踪和退潮状态细分
    """

    def __init__(self):
        super().__init__()
        self.state_machine = ThemeCycleStateMachine()

    async def fetch_previous_state(self, trade_date: date, subject_key: str) -> Optional[PreviousCycleState]:
        """
        获取前一日状态
        实际应从数据库查询theme_cycle_judgement_v2表
        """
        # TODO: 实现数据库查询
        # 简化：返回None表示无历史状态
        return None

    def determine_fade_status(self, current_state: str,
                             previous_state: Optional[PreviousCycleState],
                             market_inputs: ThemeCycleMarketInput,
                             strength_score: float) -> Tuple[bool, bool]:
        """
        判断退潮状态细分
        返回：(fade_watch, fade_confirmed)
        """
        if current_state != "fade":
            return False, False

        if previous_state is None:
            return True, False  # 首次退潮，进入观察

        # 检查退潮确认条件
        if previous_state.fade_watch:
            # 连续退潮观察，检查是否确认
            if (strength_score < 30 and
                market_inputs.limit_up_count == 0 and
                market_inputs.strong_stock_count == 0):
                return False, True  # 退潮确认
            else:
                return True, False  # 保持观察

        # 首次进入退潮
        return True, False

    def build_enhanced_judgement(self,
                                trade_date: str,
                                mainline: ThemeCycleMainlineInput,
                                market: ThemeCycleMarketInput,
                                recent: ThemeCycleRecentInput,
                                previous_state: Optional[PreviousCycleState] = None,
                                strength_score: float = 50.0) -> ThemeCycleJudgement:
        """
        构建增强版周期判定
        集成状态机追踪和退潮状态细分
        """
        # 1. 使用原有逻辑计算基础周期阶段
        raw_stage, action_bias, conclusion = self.classify_primary_stage(mainline, market, recent)

        # 2. 应用状态机转换
        trade_date_obj = date.fromisoformat(trade_date)
        final_stage, fade_status, transition_reason = self.state_machine.transition(
            previous_state, raw_stage, market, strength_score
        )

        # 3. 确定退潮状态细分
        fade_watch = fade_status == "fade_watch"
        fade_confirmed = fade_status == "fade_confirmed"

        # 4. 构建基础判定
        base_judgement = super().build_judgement(trade_date, mainline, market, recent)

        # 5. 增强结果
        enhanced_dict = base_judgement.__dict__.copy()

        # 更新周期阶段为最终状态
        enhanced_dict["primary_cycle_stage"] = final_stage

        # 更新布尔字段（兼容原有字段）
        enhanced_dict["is_fade"] = final_stage == "fade"

        # 添加增强字段到source_trace
        enhanced_trace = enhanced_dict.get("source_trace", {}).copy()
        enhanced_trace.update({
            "previous_cycle_state": previous_state.cycle_state if previous_state else None,
            "state_transition_reason": transition_reason,
            "fade_status": fade_status,
            "fade_watch": fade_watch,
            "fade_confirmed": fade_confirmed,
            "raw_stage": raw_stage,
            "final_stage": final_stage,
            "mainline_strength_score": strength_score,
        })

        enhanced_dict["source_trace"] = enhanced_trace
        enhanced_dict["source_version"] = "theme_cycle_judgement.enhanced.v1"

        return ThemeCycleJudgement(**enhanced_dict)

    def build_enhanced_with_strength(self,
                                    trade_date: str,
                                    mainline: ThemeCycleMainlineInput,
                                    market: ThemeCycleMarketInput,
                                    recent: ThemeCycleRecentInput,
                                    strength_score: float) -> ThemeCycleJudgement:
        """
        构建增强版判定（包含主线强度评分）
        简化版本，假设无历史状态
        """
        # 获取历史状态（简化：None）
        previous_state = None

        return self.build_enhanced_judgement(
            trade_date=trade_date,
            mainline=mainline,
            market=market,
            recent=recent,
            previous_state=previous_state,
            strength_score=strength_score
        )


# 兼容性包装器
def build_cycle_judgement(trade_date: str,
                         mainline: ThemeCycleMainlineInput,
                         market: ThemeCycleMarketInput,
                         recent: ThemeCycleRecentInput,
                         enhanced: bool = False,
                         strength_score: Optional[float] = None) -> ThemeCycleJudgement:
    """
    兼容性包装函数
    enhanced=True时使用增强版，否则使用原版
    """
    if enhanced:
        service = EnhancedCycleJudgementService()
        if strength_score is not None:
            return service.build_enhanced_with_strength(trade_date, mainline, market, recent, strength_score)
        else:
            return service.build_enhanced_judgement(trade_date, mainline, market, recent)
    else:
        service = CycleJudgementService()
        return service.build_judgement(trade_date, mainline, market, recent)