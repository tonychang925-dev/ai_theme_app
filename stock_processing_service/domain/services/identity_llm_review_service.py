from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class IdentityLLMReviewVerdict:
    verdict: str
    confidence: Decimal
    reason: str


class IdentityLLMReviewService:
    """Layer A LLM 复核服务。

    设计文档 §3.2 硬规则：
      - is_main_theme = rule_is_main_theme AND llm_applied AND llm_is_main_theme=true
      - 任一失败则降为 observed
      - 升级触发仅允许进入 review_pending

    当前为确定性复核（无 LLM API 接入时），使用规则引擎输出 + K 线证据做结构化判定。
    后续接入真实 LLM 时，替换 review_with_rule() 为 API 调用。
    """

    def review(self, composite_score: Decimal, one_day_tour_flag: bool) -> IdentityLLMReviewVerdict:
        """简化接口（向后兼容），委托给复合判定。"""
        return self._deterministic_review(
            composite_score=composite_score,
            one_day_tour_flag=one_day_tour_flag,
            logic_ok=False,
            market_ok=False,
            rule_is_main_theme=False,
        )

    def review_with_rule(
        self,
        composite_score: Decimal,
        one_day_tour_flag: bool,
        logic_ok: bool,
        market_ok: bool,
        rule_is_main_theme: bool,
    ) -> IdentityLLMReviewVerdict:
        """使用完整规则引擎输出的复核。"""
        return self._deterministic_review(
            composite_score=composite_score,
            one_day_tour_flag=one_day_tour_flag,
            logic_ok=logic_ok,
            market_ok=market_ok,
            rule_is_main_theme=rule_is_main_theme,
        )

    @staticmethod
    def _deterministic_review(
        *,
        composite_score: Decimal,
        one_day_tour_flag: bool,
        logic_ok: bool,
        market_ok: bool,
        rule_is_main_theme: bool,
    ) -> IdentityLLMReviewVerdict:
        # ── 一日游硬否决 ──
        if one_day_tour_flag:
            return IdentityLLMReviewVerdict(
                verdict="review_pending",
                confidence=Decimal("0.55"),
                reason="one_day_tour_risk",
            )

        # ── 双门禁通过 → confirmed（设计文档 §3.2：is_main_theme = rule_is_main_theme AND llm_applied AND llm_is_main_theme）──
        if rule_is_main_theme:
            return IdentityLLMReviewVerdict(
                verdict="confirmed",
                confidence=Decimal("0.85"),
                reason="rule_both_gates_passed",
            )

        # ── 事件维度通过但市场不认可 → review_pending（设计文档 §3.5 升级触发器路径）──
        if logic_ok and not market_ok and composite_score >= Decimal("50"):
            return IdentityLLMReviewVerdict(
                verdict="review_pending",
                confidence=Decimal("0.60"),
                reason="logic_ok_but_market_weak",
            )

        # ── 高分边界（70+ 但规则未完全通过）→ review_pending ──
        if composite_score >= Decimal("70"):
            return IdentityLLMReviewVerdict(
                verdict="review_pending",
                confidence=Decimal("0.55"),
                reason="high_composite_borderline",
            )

        # ── 中等分数 + 有事件证据 → observed（有可能成为主线，继续观察）──
        if logic_ok and composite_score >= Decimal("40"):
            return IdentityLLMReviewVerdict(
                verdict="observed",
                confidence=Decimal("0.65"),
                reason="event_evidence_present",
            )

        # ── 底分 → observed（后续由 IdentityDecider 根据 inactive 门槛过滤）──
        return IdentityLLMReviewVerdict(
            verdict="observed",
            confidence=Decimal("0.70"),
            reason="low_score_keep_observed",
        )

    def build_llm_prompt(
        self,
        *,
        trade_date: str,
        subject_key: str,
        subject_name: str,
        rule_input: Any,
        rule_output: Any,
        one_day_tour_flag: bool,
        kline_result: Any = None,
    ) -> str:
        """构建 LLM 复核提示词（1:1 复刻生产 _build_llm_prompt()）。

        当前用于诊断/日志输出，后续接入真实 LLM 时使用。
        """
        r = rule_output  # IdentityRuleResult
        return f"""你是A股主线身份判定复核专家。必须严格执行以下规则：
1) 你必须同时复核"逻辑维度 + 市场维度"，不能只看单维度。
2) 逻辑维度：新颖度、时机、影响广度。
3) 市场维度：热度、板块强度（涨停潮/前排强度）、资金持续流入、事件持续发酵。
4) 禁止自由发挥，必须严格依据输入硬数据与规则阈值判断。
5) 一日游题材、单日异动、缺乏持续性的题材，不得判为主线。
6) 输出必须是JSON，不要输出额外文本。

交易日：{trade_date}
题材：{subject_name}
subject_key：{subject_key}

逻辑维度硬证据：
- logic_score={r.logic_score}
- market_score={r.market_score}
- composite_score={r.composite_score}
- one_day_tour_flag={one_day_tour_flag}

规则层预判：
- logic_ok={r.logic_ok}
- market_ok={r.market_ok}
- rule_is_main_theme={r.rule_is_main_theme}

请严格按以下硬规则阈值复核：
主线确认条件（必须同时满足）：
1. rule_is_main_theme = true（逻辑+市场双门禁通过）
2. 非一日游（one_day_tour_flag = false）
3. LLM 确认无结构性否决

输出JSON格式：
{{"is_main_theme": true/false, "confidence": 0.0-1.0, "reasons": ["..."], "risk_flags": ["..."]}}
"""
