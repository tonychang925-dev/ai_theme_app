from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NextDayWatchlistEngine:
    """Build categorized next-day watchlist with buy/invalid conditions.

    Categorises stocks from stock_decisions into:
      - 重点观察：mainline_focus themes with core leader roles
      - 弱转强观察: themes in watch_weak_to_strong / strong_branch_watch with support
      - 风险观察：risk_watch / fade_avoid themes
      - 放弃观察：everything else (excluded from output)

    Returns tuple (watchlist_rows, diagnostics) so callers can
    inspect why items were accepted or filtered out.
    """

    def build(
        self,
        *,
        theme_decisions: list[dict[str, Any]],
        stock_decisions: list[dict[str, Any]],
        market_environment: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        theme_by_key = {
            str(x.get("subject_key") or ""): x
            for x in theme_decisions
        }
        market_mode = str(market_environment.get("market_mode") or "wait")
        position_limit = float(market_environment.get("position_limit") or 0)

        # ── diagnostics counters ──
        diag = {
            "theme_decision_count": len(theme_decisions),
            "stock_decision_count": len(stock_decisions),
            "stock_with_subject_key_count": sum(
                1 for s in stock_decisions if str(s.get("subject_key") or "")
            ),
            "matched_stock_theme_count": 0,
            "filtered_by_market_mode": 0,
            "filtered_by_theme_decision": 0,
            "filtered_by_role": 0,
            "filtered_by_support_score": 0,
            "final_watchlist_count": 0,
            "theme_keys": sorted(theme_by_key.keys()),
            "unmatched_stock_keys": [] if len(stock_decisions) <= 15 else None,
        }

        unmatched_keys: set[str] = set()

        rows: list[dict[str, Any]] = []
        for stock in stock_decisions:
            subject_key = str(stock.get("subject_key") or "")
            if not subject_key:
                continue

            theme = theme_by_key.get(subject_key)
            if not theme:
                if len(rows) < 20:
                    unmatched_keys.add(subject_key)
                continue

            diag["matched_stock_theme_count"] += 1

            if market_mode == "wait":
                diag["filtered_by_market_mode"] += 1
                continue

            theme_decision = str(theme.get("decision") or "")
            role = str(stock.get("role") or "")
            support_score = float(stock.get("support_score") or 0)

            # P1: mild relaxation — strong_branch_watch + watch role → 弱转强观察
            #      support_score threshold lowered from 60 → 40
            if theme_decision in {"reject"}:
                diag["filtered_by_theme_decision"] += 1
                continue

            if role == "reject":
                diag["filtered_by_role"] += 1
                continue

            category = self._category(theme_decision, role, support_score, market_mode)
            if category == "放弃观察":
                if support_score < 40:
                    diag["filtered_by_support_score"] += 1
                else:
                    diag["filtered_by_role"] += 1
                continue

            rows.append({
                "category": category,
                "priority": self._priority(category, stock),
                "stock_id": stock.get("stock_id"),
                "stock_code": stock.get("stock_code") or stock.get("stock_id"),
                "stock_name": stock.get("stock_name"),
                "subject_key": subject_key,
                "theme_name": stock.get("theme_name") or theme.get("theme_name"),
                "role_label": stock.get("role_label"),
                "stage": theme.get("cycle_stage"),
                "action": self._action(category),
                "buy_condition": stock.get("buy_condition") or ["等待竞价确认"],
                "invalid_condition": stock.get("invalid_condition") or ["不满足承接条件则放弃"],
                "risk_level": self._risk_level(category, market_mode),
                "suggested_position": min(
                    position_limit, self._suggested_position(category)
                ),
                "reason": self._reason(category, theme, stock),
            })

        rows.sort(key=lambda x: int(x.get("priority") or 999))
        rows = rows[:30]
        diag["final_watchlist_count"] = len(rows)
        diag["unmatched_stock_keys"] = sorted(unmatched_keys)

        return rows, diag

    @staticmethod
    def _category(
        theme_decision: str,
        role: str,
        support_score: float,
        market_mode: str,
    ) -> str:
        if market_mode == "wait":
            return "放弃观察"
        if theme_decision == "mainline_focus" and role in {
            "leader", "sub_leader", "switch_leader",
        }:
            return "重点观察"
        if theme_decision in {"watch_weak_to_strong", "strong_branch_watch"} and support_score >= 40:
            return "弱转强观察"
        if theme_decision in {"risk_watch", "fade_avoid"}:
            return "风险观察"
        if theme_decision == "mainline_focus":
            return "弱转强观察"
        return "放弃观察"

    @staticmethod
    def _priority(category: str, stock: dict[str, Any]) -> int:
        base = {
            "重点观察": 1,
            "弱转强观察": 10,
            "风险观察": 50,
        }.get(category, 99)
        score = float(stock.get("core_score") or 0)
        return base + max(0, 20 - int(score // 5))

    @staticmethod
    def _action(category: str) -> str:
        return {
            "重点观察": "重点盯盘，满足承接条件后关注",
            "弱转强观察": "仅竞价确认后关注",
            "风险观察": "只观察风险，不主动开仓",
        }.get(category, "观察")

    @staticmethod
    def _risk_level(category: str, market_mode: str) -> str:
        if category == "风险观察":
            return "high"
        if market_mode == "defense":
            return "medium"
        return "low"

    @staticmethod
    def _suggested_position(category: str) -> float:
        return {
            "重点观察": 0.3,
            "弱转强观察": 0.2,
            "风险观察": 0.0,
        }.get(category, 0.0)

    @staticmethod
    def _reason(
        category: str,
        theme: dict[str, Any],
        stock: dict[str, Any],
    ) -> str:
        return (
            f"{category}：{theme.get('action_advice') or ''}；"
            f"{stock.get('rationale') or ''}"
        ).strip("；")
