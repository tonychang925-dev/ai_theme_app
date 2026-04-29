from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class IdentityDecision:
    identity_status: str
    final_score: Decimal
    reason: str


class IdentityDecider:
    """Layer A 身份决策器。

    对应设计文档 §3.2 硬规则：
      - is_main_theme = rule_is_main_theme AND llm_applied AND llm_is_main_theme=true
      - 任一失败则降为 observed
      - 不满足最低门槛（logic_ok=false 且 composite<40）→ inactive

    identity_status 取值（设计文档 §3.2）:
      confirmed / observed / review_pending / manual_override / inactive
    """

    # 设计文档 §3.5: logic_ok 要求 strong_event_count_7d>=1, event_count_3d>=1, event_recency_days<=5
    # 若连基础事件门槛都不满足且综合分过低，不应进入观察池。
    _OBSERVED_MIN_COMPOSITE = Decimal("40")

    def decide(
        self,
        composite_score: Decimal,
        llm_verdict: str,
        one_day_tour_flag: bool,
        logic_ok: bool = False,
        rule_is_main_theme: bool = False,
        platform_breakout_flag: bool = False,
    ) -> IdentityDecision:
        # ── 硬门禁：设计文档 §3.2 ──
        if one_day_tour_flag and llm_verdict == "confirmed":
            return IdentityDecision(
                identity_status="review_pending",
                final_score=composite_score,
                reason="confirmed_but_tour_risk",
            )
        if llm_verdict == "confirmed":
            return IdentityDecision(
                identity_status="confirmed",
                final_score=composite_score,
                reason="llm_confirmed",
            )
        if llm_verdict == "review_pending":
            return IdentityDecision(
                identity_status="review_pending",
                final_score=composite_score,
                reason="llm_review_pending",
            )

        # ── 升级触发器：设计文档 §3.2.1 ──
        # 非主线题材出现强化信号（规则/板块/K线）→ review_pending 排队复核
        # 禁止 upgrade_trigger → confirmed 直通
        if rule_is_main_theme:
            # 规则双门禁通过但 LLM/decider 未确认 → 必须复核
            return IdentityDecision(
                identity_status="review_pending",
                final_score=composite_score,
                reason="upgrade_rule_both_gates_passed",
            )
        if logic_ok and composite_score >= Decimal("60"):
            # 事件证据充分 + 综合分达标 → 值得复核
            return IdentityDecision(
                identity_status="review_pending",
                final_score=composite_score,
                reason="upgrade_logic_ok_high_composite",
            )
        if platform_breakout_flag and composite_score >= Decimal("50"):
            # 平台突破 + 中等综合分 → 结构信号值得关注
            return IdentityDecision(
                identity_status="review_pending",
                final_score=composite_score,
                reason="upgrade_platform_breakout",
            )

        # ── 最低观察门槛：设计文档 §3.2 定义 identity_status 含 inactive ──
        if composite_score >= self._OBSERVED_MIN_COMPOSITE:
            return IdentityDecision(
                identity_status="observed",
                final_score=composite_score,
                reason="llm_observed",
            )
        if logic_ok and composite_score >= Decimal("25"):
            return IdentityDecision(
                identity_status="observed",
                final_score=composite_score,
                reason="observed_logic_ok_marginal",
            )
        return IdentityDecision(
            identity_status="inactive",
            final_score=composite_score,
            reason="below_observed_threshold",
        )
