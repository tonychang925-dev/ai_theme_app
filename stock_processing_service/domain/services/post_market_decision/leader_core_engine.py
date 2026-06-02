from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LeaderCoreEngine:
    """Build stock-level decision reviews from strong_stock_reviews / stock_facts.

    P0 maps existing strong_stock_reviews data into decision-grade outputs.
    Does NOT require theme_leader_candidate as an independent source of truth yet.
    """

    def build(
        self,
        *,
        report_context: dict[str, Any],
        strong_stock_reviews: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        source_rows = list(strong_stock_reviews or [])
        if not source_rows:
            source_rows = list(report_context.get("stock_facts") or [])

        rows: list[dict[str, Any]] = []
        for source in source_rows[:80]:
            if not isinstance(source, dict):
                continue

            stock_id = str(source.get("stock_id") or source.get("stock_code") or "")
            stock_name = str(source.get("stock_name") or "")
            subject_key = str(source.get("subject_key") or "")
            theme_name = str(source.get("theme_name") or source.get("subject_name") or "")

            watch_score = self._float(
                source.get("watch_score")
                or source.get("leader_composite_score")
                or source.get("candidate_score")
                or 0
            )
            support_score = self._float(source.get("support_score") or 0)
            main_net_inflow = self._float(source.get("main_net_inflow") or 0)

            role = self._role(source, watch_score)
            role_label = self._role_label(role)

            core_score = round(
                watch_score * 0.45
                + max(0, min(100, support_score)) * 0.25
                + self._capital_score(main_net_inflow) * 0.30,
                2,
            )

            next_day_action = (
                "auction_confirm_only"
                if role in {"leader", "sub_leader", "switch_leader"}
                else "observe_only"
            )

            rows.append({
                "stock_id": stock_id,
                "stock_code": stock_id,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "role": role,
                "role_label": role_label,
                "candidate_level": str(
                    source.get("candidate_level")
                    or source.get("pool_entry_type")
                    or "unknown"
                ),
                "core_score": core_score,
                "watch_score": watch_score,
                "capital_score": self._capital_score(main_net_inflow),
                "structure_score": support_score or watch_score,
                "support_score": support_score,
                "money_flow": {
                    "main_net_inflow": main_net_inflow,
                    "money_flow_tier": source.get("money_flow_tier"),
                },
                "kline": {
                    "position_label": source.get("position_label") or source.get("support_type"),
                    "pattern_labels": source.get("pattern_labels")
                    if isinstance(source.get("pattern_labels"), list)
                    else [],
                },
                "support": {
                    "support_type": source.get("support_type"),
                    "support_score": support_score,
                    "support_reason": "已有支撑信号" if support_score > 0 else "",
                },
                "next_day_action": next_day_action,
                "buy_condition": self._buy_condition(next_day_action),
                "invalid_condition": self._invalid_condition(),
                "rationale": self._rationale(role, support_score, main_net_inflow),
                "diagnostics": {
                    "source": "strong_stock_reviews_or_report_context.stock_facts",
                    "fallback_used": [],
                },
            })

        rows.sort(key=lambda x: float(x.get("core_score") or 0), reverse=True)
        return rows[:50]

    @staticmethod
    def _role(source: dict[str, Any], watch_score: float) -> str:
        raw = str(
            source.get("role")
            or source.get("role_label")
            or source.get("role_enhanced")
            or ""
        ).lower()
        if "leader" in raw or "龙头" in raw:
            return "leader"
        if "龙二" in raw or "sub" in raw:
            return "sub_leader"
        if "卡位" in raw or "switch" in raw:
            return "switch_leader"
        if watch_score >= 80:
            return "leader"
        if watch_score >= 70:
            return "sub_leader"
        if watch_score >= 55:
            return "watch"
        return "reject"

    @staticmethod
    def _role_label(role: str) -> str:
        return {
            "leader": "龙头",
            "sub_leader": "龙二",
            "switch_leader": "卡位",
            "watch": "观察",
            "reject": "淘汰",
        }.get(role, "观察")

    @staticmethod
    def _capital_score(main_net_inflow: float) -> float:
        if main_net_inflow > 50_000_000:
            return 90.0
        if main_net_inflow > 10_000_000:
            return 75.0
        if main_net_inflow > 0:
            return 60.0
        if main_net_inflow < 0:
            return 30.0
        return 50.0

    @staticmethod
    def _buy_condition(action: str) -> list[str]:
        if action == "auction_confirm_only":
            return ["竞价不能明显低于预期", "量能温和放大", "题材前排不能集体走弱"]
        return ["继续观察，不满足条件不开仓"]

    @staticmethod
    def _invalid_condition() -> list[str]:
        return ["低开低走", "跌破关键支撑", "板块前排集体走弱"]

    @staticmethod
    def _rationale(role: str, support_score: float, main_net_inflow: float) -> str:
        parts = [f"角色={role}"]
        if support_score > 0:
            parts.append("具备支撑信号")
        if main_net_inflow > 0:
            parts.append("资金为正")
        return "；".join(parts)

    @staticmethod
    def _float(value: Any) -> float:
        try:
            if value in (None, ""):
                return 0.0
            return float(value)
        except Exception:
            return 0.0
