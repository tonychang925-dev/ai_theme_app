"""P2.4 — PlaybookBuilder.

Generates MarketPlaybook from CognitionCard + DB data.
Deterministic, rule-based. No LLM. Does NOT write M8.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone
from typing import Any

DB_DSN = "postgresql://localhost:5432/stock_data_test"

# ── Phase → Strategy mapping ──

_PHASE_STRATEGY: dict[str, dict[str, Any]] = {
    "start": {
        "strategy": "观察确认，不急于入场",
        "entry_condition": "板块出现明确龙头 + 资金持续流入 + 事件刺激被市场确认",
        "exit_condition": "龙头炸板 / 板块扩散失败 / 事件被证伪",
        "invalidation_condition": "3 日内无龙头确认 → 放弃观察",
        "risk": "假启动（一日游行情）",
    },
    "fermentation": {
        "strategy": "趋势确认后右侧跟随，重点做龙头",
        "entry_condition": "龙头加速确认 + 板块扩散至跟风 + 资金加速流入",
        "exit_condition": "龙头放量破位 / 跟风大面积亏钱 / 资金流出",
        "invalidation_condition": "龙头炸板或跟风大面积回落 → 停止跟随",
        "risk": "发酵失败退回分歧",
    },
    "divergence": {
        "strategy": "等待缩量分歧结束，不追龙头",
        "entry_condition": "缩量企稳（量能降至前5日70%）+ 核心股不破关键均线 + 资金开始回流",
        "exit_condition": "分歧变成恐慌（放量+全线破位）",
        "invalidation_condition": "龙头放量破位 或 板块多只核心跌停 → 分歧升级为退潮",
        "risk": "分歧升级为退潮 / 外部冲击打断修复",
    },
    "repair": {
        "strategy": "分歧结束后做修复，优先核心龙头",
        "entry_condition": "修复信号确认（资金回流+龙头再走强+K线修复）",
        "exit_condition": "修复失败（龙头破位、资金重新流出）",
        "invalidation_condition": "修复后龙头无法新高 → 弱修复，减仓",
        "risk": "修复失败退回分歧 / 弱修复后再次退潮",
    },
    "fade_watch": {
        "strategy": "谨慎观望，防范退潮，只做反弹不追趋势",
        "entry_condition": "退潮确认信号被证伪 + 板块出现承接 + 外部锚定转强",
        "exit_condition": "退潮确认 / 龙头继续破位 / 外围恶化",
        "invalidation_condition": "退潮确认信号出现 → 清仓回避",
        "risk": "退潮加速 / 板块内恐慌扩散 / 外围崩盘",
    },
    "fade_confirmed": {
        "strategy": "回避，等待新方向出现",
        "entry_condition": "冰点信号出现（极度缩量+全线悲观+龙头企稳）+ 新事件刺激",
        "exit_condition": "已无仓位 → 仅观察",
        "invalidation_condition": "无 — 当前不应持仓",
        "risk": "持续阴跌 / 情绪冰点后无反弹",
    },
}

_DEFAULT_PLAYBOOK = {
    "strategy": "观察等待",
    "entry_condition": "方向确认后再入场",
    "exit_condition": "不符合预期时离场",
    "invalidation_condition": "支撑逻辑被证伪时清仓",
    "risk": "方向判断错误",
}


class PlaybookBuilder:
    """Generate MarketPlaybook from CognitionCard data.

    Usage:
        builder = PlaybookBuilder()
        playbook = builder.build(cognition_card)
    """

    def build(self, cognition_card: dict[str, Any]) -> dict[str, Any]:
        phase = cognition_card.get("phase_raw", "start")
        template = _PHASE_STRATEGY.get(phase, _DEFAULT_PLAYBOOK)

        # Derive watchpoints from cognition context
        watchpoints = self._derive_watchpoints(cognition_card, phase)

        return {
            "trade_date": cognition_card.get("trade_date", ""),
            "subject_id": cognition_card.get("subject_id", ""),
            "subject_name": cognition_card.get("subject_name", ""),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ai_draft": True,
            "analyst_reviewed": False,

            "phase": phase,
            "phase_label": cognition_card.get("market_phase", phase),
            "strategy": template["strategy"],
            "entry_condition": template["entry_condition"],
            "exit_condition": template["exit_condition"],
            "invalidation_condition": template["invalidation_condition"],
            "tomorrow_watchpoints": watchpoints,
            "key_risk": template["risk"],

            "analyst_overrides": {},
        }

    # ── Review: compare yesterday's expectations with today's reality ──

    def build_review(
        self,
        cognition_card: dict[str, Any],
        prev_cognition_card: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build review comparing prediction vs actual."""
        yv = cognition_card.get("yesterday_view", "")
        ta = cognition_card.get("today_actual", "")

        review = {
            "yesterday_prediction": yv,
            "today_actual": ta,
            "prediction_correct": None,  # None = analyst must judge
            "prediction_delta": "",
        }

        if prev_cognition_card:
            prev_tv = prev_cognition_card.get("tomorrow_view", "")
            review["yesterday_prediction"] = prev_tv
            review["prediction_delta"] = (
                f"昨日预测: {prev_tv[:80]}\n今日实际: {ta[:80]}"
            )

        return review

    @staticmethod
    def _derive_watchpoints(card: dict[str, Any], phase: str) -> list[str]:
        """Derive tomorrow's watchpoints from phase and card context."""
        wp: list[str] = []

        if phase == "start":
            wp = [
                "□ 龙头是否确认（涨停/连板）",
                "□ 板块是否扩散至跟风",
                "□ 资金是否持续流入",
                "□ 事件刺激是否被市场验证",
            ]
        elif phase == "fermentation":
            wp = [
                "□ 龙头是否继续加速",
                "□ 跟风是否跟进（不回落）",
                "□ 成交额是否放大（健康量能）",
                "□ 是否出现首次分歧信号",
            ]
        elif phase == "divergence":
            wp = [
                "□ 缩量是否持续（量能 < 前5日70%）",
                "□ 核心股是否守住关键均线",
                "□ 资金是否开始回流",
                "□ 外部锚定是否稳定（韩国/美股）",
            ]
        elif phase == "repair":
            wp = [
                "□ 修复是否确认（龙头再走强）",
                "□ 资金是否持续回流",
                "□ 是否出现加速信号（弱转强）",
                "□ 龙头能否创新高",
            ]
        elif phase in ("fade_watch", "fade_confirmed"):
            wp = [
                "□ 退潮是否确认（更多核心股破位）",
                "□ 是否出现冰点信号（极度缩量）",
                "□ 新事件是否出现",
                "□ 外部锚定是否恶化",
            ]
        else:
            wp = [
                "□ 方向是否确认",
                "□ 龙头是否明确",
                "□ 资金是否配合",
                "□ 风险是否可控",
            ]

        return wp
