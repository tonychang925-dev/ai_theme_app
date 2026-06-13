"""P3-B: OneToTwoTechnicalSummaryFormatter — natural-language K-line summary.

Reads structured kline_pattern_quality facts and produces human-readable
technical-form summaries. Does NOT modify GoldenSpiderPatternService,
TechnicalGate, or any decision-making code.

Input: kline_pattern_quality dict + technical_structure_score + risk_flags
Output: structured technical_summary with label, score, reason, highlights, risks.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


class OneToTwoTechnicalSummaryFormatter:
    """Format K-line technical facts into human-readable summary.

    Pure formatter — no I/O, no mutation, no decision logic.
    """

    # ── supported technical reasons → human labels ──

    REASON_LABELS: dict[str, str] = {
        "insufficient_history": "K线历史数据不足",
        "not_above_ma_cluster": "收盘价未站上均线簇",
        "ma_not_bullish_alignment": "均线未形成多头排列",
        "ma_cluster_not_converged": "均线簇未收敛",
        "volume_not_expanding": "量能未有效放大",
        "near_resistance": "接近压力位",
        "support_broken": "支撑已破坏",
        "score_below_threshold": "技术评分未达阈值",
    }

    def format(
        self,
        kline_pattern_quality: dict[str, Any] | None,
        *,
        technical_structure_score: float | None = None,
        risk_flags: list[str] | None = None,
        veto_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        kpq = dict(kline_pattern_quality or {})
        has_gs = bool(kpq.get("has_golden_spider"))
        level = str(kpq.get("level") or "unknown")
        kline_score = kpq.get("score")
        tech_reason = str(kpq.get("technical_reason") or "")
        kline_data_ready = bool(kpq.get("kline_data_ready"))

        # ── label ──
        if not kline_data_ready:
            label = "K线数据不足，无法评估技术形态"
        elif has_gs and level == "golden":
            label = "金蜘蛛形态成立，技术结构健康"
        elif level == "near_golden":
            label = "近金蜘蛛形态，技术结构偏强"
        elif not has_gs:
            label = "技术形态未完全确认"

        # ── highlights ──
        highlights = self._build_highlights(kpq)

        # ── risks ──
        risks = self._build_risks(kpq, has_gs, risk_flags or [], veto_reasons or [])

        return {
            "label": label,
            "score": (
                round(float(Decimal(str(technical_structure_score))), 1)
                if technical_structure_score is not None
                else (round(float(Decimal(str(kline_score))), 1) if kline_score else None)
            ),
            "reason": tech_reason or None,
            "reason_label": self.REASON_LABELS.get(tech_reason, tech_reason) if tech_reason else None,
            "highlights": highlights,
            "risks": risks,
            "has_golden_spider": has_gs,
            "level": level if level != "unknown" else None,
            "kline_data_ready": kline_data_ready,
        }

    def _build_highlights(self, kpq: dict[str, Any]) -> list[str]:
        highlights: list[str] = []
        has_gs = bool(kpq.get("has_golden_spider"))
        level = str(kpq.get("level") or "")

        if has_gs and level == "golden":
            highlights.append("均线簇收敛后向上发散，金蜘蛛形态确认")
        elif level == "near_golden":
            highlights.append("均线有收敛迹象，接近金蜘蛛形态")

        above_ma5 = kpq.get("above_ma5")
        above_ma10 = kpq.get("above_ma10")
        above_ma20 = kpq.get("above_ma20")
        ma_status = str(kpq.get("ma_alignment_status") or "")

        if above_ma5 and above_ma10 and above_ma20:
            highlights.append("收盘价站上 MA5/MA10/MA20")
        elif above_ma5 is True:
            highlights.append("收盘价站上 MA5")
        elif above_ma5 is False and kpq.get("kline_data_ready"):
            highlights.append("收盘价低于 MA5")

        if ma_status == "均线多头":
            highlights.append("均线呈多头排列")

        if not kpq.get("support_broken") and kpq.get("kline_data_ready"):
            if kpq.get("kline_near_support"):
                highlights.append("靠近支撑位但未破位")

        trend = str(kpq.get("kline_trend_state") or "")
        if trend in ("bullish_trend", "uptrend"):
            highlights.append("处于上升趋势")
        elif trend in ("consolidation", "sideways"):
            highlights.append("处于横盘整理")

        pos_label = str(kpq.get("position_label") or "")
        if pos_label in ("突破前高", "接近前高"):
            highlights.append(f"位置信号: {pos_label}")

        if not highlights:
            highlights.append("暂无显著技术亮点")
        return highlights

    def _build_risks(
        self,
        kpq: dict[str, Any],
        has_gs: bool,
        risk_flags: list[str],
        veto_reasons: list[str],
    ) -> list[str]:
        risks: list[str] = []

        if kpq.get("support_broken"):
            risks.append("支撑已破坏，存在下行风险")
        if kpq.get("kline_near_resistance") or kpq.get("near_pressure"):
            risks.append("接近压力位，存在阻力风险")
        if kpq.get("is_downtrend"):
            risks.append("处于下降趋势")
        if not has_gs and kpq.get("kline_data_ready"):
            score = kpq.get("score")
            if score is not None:
                try:
                    if float(score) < 55:
                        risks.append(f"技术评分偏低（{float(score):.0f}），暂不作为强 focus")
                except (ValueError, TypeError):
                    pass
            else:
                risks.append("均线结构未完全确认，暂不作为强 focus")

        # Absorb relevant risk_flags from TechnicalGate
        for rf in risk_flags:
            if "技术" in rf or "K线" in rf or "均线" in rf or "支撑" in rf or "压力" in rf:
                if rf not in risks:
                    risks.append(rf)

        for v in veto_reasons:
            if v in ("下降趋势", "支撑破坏"):
                if v not in risks:
                    risks.append(v)

        if not risks:
            risks.append("暂无明显技术风险")
        return risks
