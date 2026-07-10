"""Phase 4.5.4 T02 — ChartReviewBuilder.

Converts raw analyst-charts JSON into structured market_chart_reviews[].
Deterministic rules only. No LLM.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ═══ Chart type -> (title, field mapping, status rules) ═══

CHART_SPECS: dict[str, dict] = {
    "market_breadth": {
        "title": "市场宽度",
        "key_metrics": ["up_count", "down_count", "limit_up_count", "limit_down_count"],
        "status_fn": "_breadth_status",
    },
    "emotion_momentum": {
        "title": "情绪动能",
        "key_metrics": ["emotion_momentum_score", "label",
                        "first_board_red_ratio", "chain_board_big_loss_ratio"],
        "status_fn": "_momentum_status",
    },
    "active_capital": {
        "title": "活跃资金",
        "key_metrics": ["active_amount_yi", "total_amount_yi",
                        "limit_up_count"],
        "status_fn": "_capital_status",
    },
    "relay_ecology": {
        "title": "连板接力生态",
        "key_metrics": ["max_board_height", "promotion_1_to_2",
                        "promotion_2_to_3", "feedback_score", "feedback_label"],
        "status_fn": "_relay_status",
    },
    "institution_style": {
        "title": "机构风格",
        "key_metrics": [],
        "status_fn": "_style_status",
    },
    "hot_money_style": {
        "title": "游资风格",
        "key_metrics": [],
        "status_fn": "_style_status",
    },
}


class ChartReviewBuilder:
    """Build market_chart_reviews from analyst-charts JSON array."""

    def build(self, charts: list[dict]) -> list[dict[str, Any]]:
        if not charts:
            return []

        # Index charts by type
        by_type: dict[str, dict] = {}
        for c in charts:
            ct = c.get("chart_type", "")
            if ct:
                by_type[ct] = c

        reviews: list[dict[str, Any]] = []
        for chart_type, spec in CHART_SPECS.items():
            chart = by_type.get(chart_type)
            if chart is None:
                continue
            data = chart.get("data") or {}
            interpretation = chart.get("interpretation", "")

            review: dict[str, Any] = {
                "chart_type": chart_type,
                "title": spec["title"],
                "status": "",
                "score": None,
                "summary": "",
                "key_metrics": {},
                "evidence": [],
                "analyst_note": "",
                "source_quality": 1.0,
            }

            # Extract key metrics
            for k in spec["key_metrics"]:
                if k in data:
                    review["key_metrics"][k] = data[k]

            # Determine status and score
            fn_name = spec.get("status_fn", "")
            status_fn = getattr(self, fn_name, None)
            if status_fn:
                review["status"], review["score"] = status_fn(data)

            # Generate summary
            summary_fn = getattr(self, f"_summary_{chart_type}", None)
            if summary_fn:
                review["summary"] = summary_fn(data, review)

            # Evidence from interpretation
            if interpretation:
                review["evidence"] = [interpretation[:200]]

            # Source quality
            review["source_quality"] = (
                0.8 if data else 0.3
            )

            reviews.append(review)

        return reviews

    # ═══ Status functions ═══

    @staticmethod
    def _breadth_status(data: dict) -> tuple[str, float | None]:
        score = data.get("composite_score", 0)
        if score is None:
            score = 0
        if score >= 2:
            return "活跃", float(score)
        elif score >= -5:
            return "中性", float(score)
        else:
            return "收缩", float(score)

    @staticmethod
    def _momentum_status(data: dict) -> tuple[str, float | None]:
        score = data.get("emotion_momentum_score", 0)
        if score is None:
            score = 0
        if score > 5:
            return "亢奋", float(score)
        elif score > 0:
            return "正常", float(score)
        elif score > -5:
            return "退潮", float(score)
        else:
            return "冰点", float(score)

    @staticmethod
    def _capital_status(data: dict) -> tuple[str, float | None]:
        label = data.get("label", "")
        active = data.get("active_amount_yi") or 0
        total = data.get("total_amount_yi") or 1
        ratio = active / max(total, 1)
        if "大幅流入" in label or ratio > 0.15:
            return "回流", float(ratio)
        elif "流出" in label or ratio < 0.05:
            return "流出", float(ratio)
        else:
            return "中性", float(ratio)

    @staticmethod
    def _relay_status(data: dict) -> tuple[str, float | None]:
        fb = data.get("feedback_score", 0)
        if fb is None:
            fb = 0
        if fb > 0:
            return "改善", float(fb)
        elif fb < -10:
            return "恶化", float(fb)
        else:
            return "中性", float(fb)

    @staticmethod
    def _style_status(data: dict) -> tuple[str, float | None]:
        directions = data.get("directions") or []
        if not directions:
            return "无数据", None
        # Majority state
        states = [d.get("state", "") for d in directions]
        active_count = sum(
            1 for s in states
            if any(kw in s for kw in ("启动", "修复", "关注", "主升", "加速"))
        )
        adjust_count = sum(
            1 for s in states
            if any(kw in s for kw in ("调整", "退潮", "淘汰"))
        )
        if active_count >= len(states) * 0.5:
            return "偏积极", None
        elif adjust_count >= len(states) * 0.5:
            return "偏防御", None
        else:
            return "中性", None

    # ═══ Summary functions ═══

    @staticmethod
    def _summary_market_breadth(data: dict, review: dict) -> str:
        up = data.get("up_count") or 0
        down = data.get("down_count") or 0
        lu = data.get("limit_up_count") or 0
        ld = data.get("limit_down_count") or 0
        total = up + down or 1
        up_ratio = round(up / total * 100, 1)
        return (
            f"今日上涨{up_ratio}%（{up}/{total}），涨停{lu}家/跌停{ld}家，"
            f"市场宽度{review['status']}。"
        )

    @staticmethod
    def _summary_emotion_momentum(data: dict, review: dict) -> str:
        score = data.get("emotion_momentum_score", 0) or 0
        label = data.get("label", "")
        fb_red = (data.get("first_board_red_ratio") or 0) * 100
        cl_loss = (data.get("chain_board_big_loss_ratio") or 0) * 100
        return (
            f"情绪动能{score:.1f}，{label}。"
            f"首板红盘比{fb_red:.0f}%，连板大面比{cl_loss:.0f}%。"
        )

    @staticmethod
    def _summary_active_capital(data: dict, review: dict) -> str:
        active = data.get("active_amount_yi") or 0
        total = data.get("total_amount_yi") or 1
        ratio = round(active / max(total, 1) * 100, 1)
        label = data.get("label", "")
        return (
            f"活跃资金{active:.0f}亿，占全市场{ratio}%。{label}。"
        )

    @staticmethod
    def _summary_relay_ecology(data: dict, review: dict) -> str:
        max_h = data.get("max_board_height") or 0
        p1to2 = (data.get("promotion_1_to_2") or 0) * 100
        fb_label = data.get("feedback_label", "")
        return (
            f"最高{max_h}板，1→2晋级率{p1to2:.0f}%。{fb_label}。"
        )

    @staticmethod
    def _summary_institution_style(data: dict, review: dict) -> str:
        directions = data.get("directions") or []
        if not directions:
            return "暂无机构风格数据。"
        top = directions[:3]
        parts = [f"{d.get('name', '?')}（{d.get('state', '?')}）" for d in top]
        return f"机构方向：{'、'.join(parts)}。"

    @staticmethod
    def _summary_hot_money_style(data: dict, review: dict) -> str:
        directions = data.get("directions") or []
        if not directions:
            return "暂无游资风格数据。"
        top = directions[:3]
        parts = [f"{d.get('name', '?')}（{d.get('state', '?')}）" for d in top]
        return f"游资方向：{'、'.join(parts)}。"
