from __future__ import annotations

from decimal import Decimal

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures, RuleResult
from stock_processing_service.domain.services.one_to_two_rule_config import (
    OneToTwoRuleConfig,
)


class OneToTwoRuleEngine:
    """1进2 的硬门禁与计划层决策。"""

    def __init__(self, config: OneToTwoRuleConfig | None = None) -> None:
        self.config = config or OneToTwoRuleConfig.from_version(None)

    @property
    def rule_version(self) -> str:
        return self.config.rule_version

    def apply(self, f: OneToTwoFeatures) -> RuleResult:
        cfg = self.config
        veto: list[str] = []
        risk: list[str] = []

        missing_required = list(f.data_quality.get("missing_required") or [])
        if missing_required:
            return RuleResult(
                decision="reject",
                veto_reasons=[f"必需字段缺失: {missing_required}"],
                risk_flags=[],
            )

        if not f.is_confirmed_mainline and not f.is_strong_hotspot:
            veto.append("非市场主线 / 非强热点")

        first_board_type = str(getattr(f, "first_board_type", "") or "")
        if not first_board_type:
            veto.append("首板类型缺失")
        elif first_board_type not in cfg.allowed_first_board_types:
            veto.append(f"不符合首板类型: {first_board_type}")

        if f.is_one_word_board:
            veto.append("一字板，不做1进2观察")

        if f.is_late_seal:
            veto.append("尾盘偷封，辨识度不足")

        turnover_rate = f.turnover_rate
        low_turnover_tier = False
        if turnover_rate is None or turnover_rate < cfg.min_reject_turnover:
            veto.append(cfg.strict_turnover_veto_reason)
        elif turnover_rate < cfg.min_focus_turnover:
            low_turnover_tier = True
            risk.append(cfg.low_turnover_risk_flag)

        same_subject_limit_count = f.same_subject_limit_count or 0
        same_subject_strong_count = f.same_subject_strong_count or 0
        has_strict_breadth = same_subject_limit_count >= cfg.min_subject_limit_count
        has_strong_breadth = (
            cfg.allow_strong_count_breadth
            and same_subject_limit_count >= 1
            and same_subject_strong_count >= cfg.min_subject_strong_count_for_breadth
            and (not cfg.strong_count_breadth_requires_confirmed_mainline or f.is_confirmed_mainline)
        )
        soft_breadth = has_strong_breadth and not has_strict_breadth
        if not has_strict_breadth and not has_strong_breadth:
            veto.append(cfg.strict_breadth_veto_reason)
        elif soft_breadth:
            risk.append(cfg.soft_breadth_risk_flag)

        if f.position_120 is not None and f.position_120 > Decimal("0.65"):
            veto.append("首板位置过高")

        if f.is_downtrend is True:
            veto.append("下降趋势")

        if f.near_pressure is True:
            veto.append("重要压力位附近")

        if f.float_mcap is not None and f.float_mcap > Decimal("20000000000"):
            veto.append("流通市值过大")

        if f.lifecycle_state in {"fade_confirmed", "dead"}:
            veto.append(f"主线状态不可交易: {f.lifecycle_state}")

        if veto:
            return RuleResult(decision="reject", veto_reasons=veto, risk_flags=risk)

        decision: str
        if f.market_trade_mode == "no_trade" or not f.allow_trade:
            return RuleResult(
                decision="observe_only",
                veto_reasons=[],
                risk_flags=["市场环境 no_trade，不得 focus"],
            )

        if not f.is_confirmed_mainline:
            decision = "pending_review_only"
            risk.append("非 confirmed_mainline，仅保留观察，不得 focus")
        elif f.lifecycle_state in {"climax", "fade_watch"}:
            decision = "observe_only"
            risk.append(f"主线阶段 {f.lifecycle_state}，只观察不 focus")
        else:
            decision = "focus"

        if soft_breadth and decision == "focus":
            decision = cfg.soft_breadth_cap_decision
        if low_turnover_tier and decision == "focus":
            decision = cfg.low_turnover_cap_decision

        return RuleResult(decision=decision, veto_reasons=[], risk_flags=risk)
