from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ThemeDecisionEngine:
    """Build theme-level trading decisions from cycles, capital, stock_facts.

    For each subject_key in theme_context_map:
    - Computes capital_validation (positive/neutral/divergent/negative/unknown)
    - Assigns tier (mainline/strong_branch/fading/watch)
    - Decides theme_decision (mainline_focus/watch_weak_to_strong/…/reject)
    - Generates action_advice and conclusion as non-empty text
    """

    def build(
        self,
        *,
        theme_context_map: dict[str, dict[str, Any]],
        market_environment: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for subject_key, ctx in theme_context_map.items():
            cycle = dict(ctx.get("cycle") or {})
            capital = dict(ctx.get("capital") or {})
            stock_facts = list(ctx.get("stock_facts") or [])

            theme_name = (
                str(cycle.get("theme_name") or "").strip()
                or str(capital.get("theme_name") or capital.get("resolved_theme_name") or "").strip()
                or str((stock_facts[0] or {}).get("theme_name") if stock_facts else "").strip()
                or subject_key
            )

            mainline_strength = self._float(
                cycle.get("mainline_strength_score")
                or cycle.get("state_strength_score")
                or 0
            )
            fade_risk = self._float(cycle.get("fade_risk_score") or 0)
            final_state = str(cycle.get("final_cycle_state") or cycle.get("cycle_stage") or "unknown")
            alive = self._bool(cycle.get("final_mainline_alive"))

            capital_validation = self._capital_validation(capital)
            market_recognition_score = self._market_recognition_score(
                capital, stock_facts, mainline_strength
            )
            cycle_score = max(0.0, min(100.0, mainline_strength - fade_risk * 0.3))

            tier = self._tier(alive, mainline_strength, fade_risk)
            decision = self._decision(
                tier=tier,
                alive=alive,
                mainline_strength=mainline_strength,
                fade_risk=fade_risk,
                capital_validation=capital_validation,
                market_mode=str(market_environment.get("market_mode") or "wait"),
            )

            decision_score = self._decision_score(
                mainline_score=mainline_strength,
                market_environment_score=self._float(market_environment.get("market_score") or 0),
                leader_core_score=self._leader_score(stock_facts),
                setup_plan_score=self._setup_score(stock_facts),
            )

            action_advice = self._action_advice(decision)
            conclusion = self._conclusion(decision, theme_name)

            rows.append({
                "subject_key": subject_key,
                "theme_name": theme_name,
                "tier": tier,
                "decision": decision,
                "decision_score": decision_score,
                "logic_score": None,
                "market_recognition_score": market_recognition_score,
                "cycle_score": cycle_score,
                "capital_validation": capital_validation,
                "leader_health": self._leader_health(stock_facts),
                "cycle_stage": final_state,
                "final_cycle_state": final_state,
                "final_mainline_alive": alive,
                "fade_risk_score": fade_risk,
                "action_advice": action_advice,
                "position_suggestion": self._position_suggestion(decision, market_environment),
                "next_day_watch_points": self._watch_points(decision),
                "invalidation_conditions": self._invalid_conditions(decision),
                "event_chain": [],
                "leader_stocks": self._leader_stocks(stock_facts),
                "conclusion": conclusion,
                "diagnostics": {
                    "cycle_joined": bool(cycle),
                    "capital_joined": bool(capital),
                    "leader_count": len(stock_facts),
                    "fallback_used": ["logic_score.not_available"],
                },
            })

        rows.sort(key=lambda x: float(x.get("decision_score") or 0), reverse=True)
        return rows[:20]

    @staticmethod
    def _capital_validation(capital: dict[str, Any]) -> str:
        if not capital:
            return "unknown"
        total = ThemeDecisionEngine._float(
            capital.get("main_net_inflow_sum")
            or capital.get("total_inflow")
            or capital.get("main_net_inflow")
            or 0
        )
        leader = ThemeDecisionEngine._float(
            capital.get("leader_main_net_inflow")
            or capital.get("leader_inflow")
            or 0
        )
        if total > 0 and leader > 0:
            return "positive"
        if total < 0 and leader < 0:
            return "negative"
        if total <= 0 and leader > 0:
            return "divergent"
        return "neutral"

    @staticmethod
    def _decision(
        *,
        tier: str,
        alive: bool,
        mainline_strength: float,
        fade_risk: float,
        capital_validation: str,
        market_mode: str,
    ) -> str:
        if not alive and mainline_strength < 50:
            return "fade_avoid"
        if fade_risk >= 70:
            return "risk_watch"
        if tier == "mainline" and capital_validation == "positive":
            if market_mode in {"attack", "normal"}:
                return "mainline_focus"
            return "watch_weak_to_strong"
        if tier == "mainline":
            return "watch_weak_to_strong"
        if tier == "strong_branch":
            return "strong_branch_watch"
        return "reject"

    @staticmethod
    def _action_advice(decision: str) -> str:
        mapping = {
            "mainline_focus": "主线重点，优先看核心前排承接",
            "watch_weak_to_strong": "主线仍活但处于分歧，只关注核心前排弱转强",
            "strong_branch_watch": "强分支观察，等待资金继续确认",
            "risk_watch": "退潮风险上升，只观察不追涨",
            "fade_avoid": "退潮或主线失效，回避",
            "reject": "非主线或证据不足，放弃",
        }
        return mapping.get(decision, "证据不足，观察")

    @staticmethod
    def _conclusion(decision: str, theme_name: str) -> str:
        mapping = {
            "mainline_focus": f"{theme_name} 具备主线交易价值，次日重点观察核心前排。",
            "watch_weak_to_strong": f"{theme_name} 仍有主线或强分支特征，但需要次日承接确认。",
            "strong_branch_watch": f"{theme_name} 属于强分支观察方向，等待进一步市场承认。",
            "risk_watch": f"{theme_name} 退潮风险较高，只观察不追涨。",
            "fade_avoid": f"{theme_name} 主线有效性下降，暂时回避。",
            "reject": f"{theme_name} 证据不足，不纳入次日重点。",
        }
        return mapping.get(decision, f"{theme_name} 暂无明确交易结论。")

    @staticmethod
    def _tier(alive: bool, strength: float, fade_risk: float) -> str:
        if alive and strength >= 70 and fade_risk < 70:
            return "mainline"
        if strength >= 50 and fade_risk < 70:
            return "strong_branch"
        if fade_risk >= 70:
            return "fading"
        return "watch"

    @staticmethod
    def _decision_score(
        mainline_score: float,
        market_environment_score: float,
        leader_core_score: float,
        setup_plan_score: float,
    ) -> float:
        return round(
            mainline_score * 0.35
            + market_environment_score * 0.30
            + leader_core_score * 0.20
            + setup_plan_score * 0.15,
            2,
        )

    @staticmethod
    def _market_recognition_score(
        capital: dict[str, Any],
        stock_facts: list[dict[str, Any]],
        fallback: float,
    ) -> float:
        total = (
            ThemeDecisionEngine._float(capital.get("main_net_inflow_sum") or 0)
            if capital else 0
        )
        leader_count = len(stock_facts)
        score = fallback
        if total > 0:
            score += 10
        if leader_count >= 3:
            score += 10
        return max(0.0, min(100.0, score))

    @staticmethod
    def _leader_score(stock_facts: list[dict[str, Any]]) -> float:
        scores = [
            ThemeDecisionEngine._float(x.get("leader_composite_score") or 0)
            for x in stock_facts
        ]
        return max(scores) if scores else 0.0

    @staticmethod
    def _setup_score(stock_facts: list[dict[str, Any]]) -> float:
        scores = [
            ThemeDecisionEngine._float(
                x.get("support_score") or x.get("leader_composite_score") or 0
            )
            for x in stock_facts
        ]
        return max(scores) if scores else 0.0

    @staticmethod
    def _leader_health(stock_facts: list[dict[str, Any]]) -> str:
        if not stock_facts:
            return "no_leader"
        if len(stock_facts) >= 3:
            return "leader_alive_with_followers"
        return "leader_alive"

    @staticmethod
    def _leader_stocks(stock_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for sf in stock_facts[:5]:
            rows.append({
                "stock_id": str(sf.get("stock_id") or ""),
                "stock_name": str(sf.get("stock_name") or ""),
                "role": str(sf.get("role") or "watch"),
                "watch_score": ThemeDecisionEngine._float(
                    sf.get("leader_composite_score") or 0
                ),
            })
        return rows

    @staticmethod
    def _position_suggestion(
        decision: str,
        market_env: dict[str, Any],
    ) -> float:
        limit = ThemeDecisionEngine._float(market_env.get("position_limit") or 0)
        if decision == "mainline_focus":
            return min(limit, 0.5)
        if decision == "watch_weak_to_strong":
            return min(limit, 0.3)
        if decision == "strong_branch_watch":
            return min(limit, 0.2)
        return 0.0

    @staticmethod
    def _watch_points(decision: str) -> list[str]:
        if decision in {"mainline_focus", "watch_weak_to_strong"}:
            return ["龙头是否高开并承接", "板块前排是否继续走强", "跟风股是否止跌修复"]
        return ["等待资金和承接进一步确认"]

    @staticmethod
    def _invalid_conditions(decision: str) -> list[str]:
        if decision in {"mainline_focus", "watch_weak_to_strong"}:
            return ["龙头跌破关键支撑", "板块无前排承接", "市场跌停家数继续扩大"]
        return ["资金继续流出", "题材热度继续下降"]

    @staticmethod
    def _float(value: Any) -> float:
        try:
            if value in (None, ""):
                return 0.0
            return float(value)
        except Exception:
            return 0.0

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes", "y", "是"}
