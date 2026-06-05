from __future__ import annotations

from decimal import Decimal

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures, RuleResult


class OneToTwoRuleEngine:
    """1进2 的硬门禁与计划层决策。"""

    def apply(self, f: OneToTwoFeatures) -> RuleResult:
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

        if not f.is_first_limit_up:
            veto.append("不是首板")

        if f.is_one_word_board:
            veto.append("一字板，不做1进2观察")

        if f.is_late_seal:
            veto.append("尾盘偷封，辨识度不足")

        if f.turnover_rate is None or f.turnover_rate < Decimal("0.08"):
            veto.append("低换手，筹码交换不足")

        if f.same_subject_limit_count is None or f.same_subject_limit_count < 2:
            veto.append("无板块合力")

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

        if f.market_trade_mode == "no_trade" or not f.allow_trade:
            return RuleResult(
                decision="observe_only",
                veto_reasons=[],
                risk_flags=["市场环境 no_trade，不得 focus"],
            )

        if not f.is_confirmed_mainline:
            return RuleResult(
                decision="pending_review_only",
                veto_reasons=[],
                risk_flags=["非 confirmed_mainline，仅保留观察，不得 focus"],
            )

        if f.lifecycle_state in {"climax", "fade_watch"}:
            return RuleResult(
                decision="observe_only",
                veto_reasons=[],
                risk_flags=[f"主线阶段 {f.lifecycle_state}，只观察不 focus"],
            )

        return RuleResult(decision="focus", veto_reasons=[], risk_flags=risk)
