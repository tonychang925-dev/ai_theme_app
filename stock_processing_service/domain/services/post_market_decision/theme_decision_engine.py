from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThemeDecisionEngine:
    """Build theme-level trading decisions from cycles, capital, stock_facts, events.

    For each subject_key in theme_context_map:
    - Computes capital_validation (positive/neutral/divergent/negative/unknown)
    - Assigns tier (mainline/strong_branch/fading/watch)
    - Decides theme_decision (mainline_focus/watch_weak_to_strong/…/reject)
    - Generates action_advice and conclusion as non-empty text
    - P1: reject_reason + missing_fields for every reject decision
    - P1: logic_score from event_chain, can upgrade reject→strong_branch_watch
    """

    def build(
        self,
        *,
        theme_context_map: dict[str, dict[str, Any]],
        market_environment: dict[str, Any],
        event_context: dict[str, list[dict[str, Any]]] | None = None,
    ) -> list[dict[str, Any]]:
        """Build theme decision rows.

        Args:
            theme_context_map: {subject_key: {cycle, capital, stock_facts}}
            market_environment: from MarketEnvironmentEngine
            event_context: optional {subject_key: [event_dict, ...]}
        """
        event_by_key = event_context or {}
        rows: list[dict[str, Any]] = []

        for subject_key, ctx in theme_context_map.items():
            cycle = dict(ctx.get("cycle") or {})
            capital = dict(ctx.get("capital") or {})
            stock_facts = list(ctx.get("stock_facts") or [])
            events = list(event_by_key.get(subject_key) or [])

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

            # ── P1-2: logic_score from event chain ──
            event_chain = self._build_event_chain(events)
            logic_score, logic_diag = self._compute_logic_score(events, decision)
            fallback_used: list[str] = []

            # ── P1-2: logic_upgrade (conservative) ──
            original_decision = decision
            if logic_score is not None:
                fallback_used.append(f"logic_score={logic_score:.1f}")
                decision = self._apply_logic_upgrade(
                    original_decision, logic_score, tier, capital_validation
                )
                if decision != original_decision:
                    fallback_used.append(f"logic_upgrade:{original_decision}->{decision}")
            else:
                fallback_used.append("logic_score.not_available")

            decision_score = self._decision_score(
                mainline_score=mainline_strength,
                market_environment_score=self._float(market_environment.get("market_score") or 0),
                leader_core_score=self._leader_score(stock_facts),
                setup_plan_score=self._setup_score(stock_facts),
                logic_score=logic_score,
            )

            action_advice = self._action_advice(decision)
            conclusion = self._conclusion(decision, theme_name)

            # ── P1-2: reject diagnostics ──
            reject_reason = self._reject_reason(original_decision, {
                "tier": tier,
                "alive": alive,
                "mainline_strength": mainline_strength,
                "fade_risk": fade_risk,
                "capital_validation": capital_validation,
                "market_mode": market_environment.get("market_mode"),
                "logic_score": logic_score,
            })
            missing_fields = self._check_missing_fields(cycle, capital, stock_facts)

            rows.append({
                "subject_key": subject_key,
                "theme_name": theme_name,
                "tier": tier,
                "decision": decision,
                "original_decision": original_decision,
                "decision_score": decision_score,
                "logic_score": logic_score,
                "logic_diagnostics": logic_diag,
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
                "event_chain": event_chain,
                "leader_stocks": self._leader_stocks(stock_facts),
                "conclusion": conclusion,
                "reject_reason": reject_reason,
                "missing_fields": missing_fields,
                "diagnostics": {
                    "cycle_joined": bool(cycle),
                    "capital_joined": bool(capital),
                    "leader_count": len(stock_facts),
                    "event_count": len(events),
                    "fallback_used": fallback_used,
                    "input_snapshot": {
                        "mainline_strength_score": mainline_strength,
                        "fade_risk_score": fade_risk,
                        "final_mainline_alive": alive,
                        "capital_validation": capital_validation,
                        "stock_fact_count": len(stock_facts),
                    },
                },
            })

        rows.sort(key=lambda x: float(x.get("decision_score") or 0), reverse=True)
        return rows[:20]

    # ── P1-2: event_chain + logic_score ──

    @staticmethod
    def _build_event_chain(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build minimal event_chain from raw events, keeping top 3 by impact."""
        result: list[dict[str, Any]] = []
        for ev in events[:5]:
            result.append({
                "event_id": str(ev.get("event_id") or ev.get("id") or ""),
                "occurred_at": str(ev.get("occurred_at") or ev.get("event_date") or ""),
                "title": str(ev.get("title") or ev.get("name") or ""),
                "event_type": str(ev.get("event_type") or ev.get("event_level") or "unknown"),
                "impact_score": ThemeDecisionEngine._float(ev.get("impact_score") or ev.get("confidence") or 0),
                "confidence": ThemeDecisionEngine._float(ev.get("confidence") or ev.get("impact_score") or 0),
                "source_channel": str(ev.get("source_channel") or ev.get("source") or "unknown"),
            })
        result.sort(key=lambda x: float(x.get("impact_score") or 0), reverse=True)
        return result[:3]

    @classmethod
    def _compute_logic_score(
        cls,
        events: list[dict[str, Any]],
        decision: str,
    ) -> tuple[float | None, dict[str, Any]]:
        """Compute logic_score from event chain.

        Returns (score | None, diagnostics).
        Score is None when no events are available.
        """
        if not events:
            return None, {"source": "none", "event_count": 0}

        # event_level weighting
        level_map = {
            "policy": 1.0, "industry": 0.85, "technology": 0.85,
            "major_event": 0.75, "order": 0.7, "media": 0.5, "unknown": 0.4,
            "政策": 1.0, "产业": 0.85, "技术": 0.85,
            "重大事件": 0.75, "订单": 0.7, "媒体": 0.5,
        }

        scores: list[float] = []
        for ev in events[:5]:
            ev_type = str(ev.get("event_type") or ev.get("event_level") or "unknown").lower()
            level_w = level_map.get(ev_type, 0.5)
            impact = cls._float(ev.get("impact_score") or ev.get("confidence") or 0.5)
            confidence = cls._float(ev.get("confidence") or ev.get("impact_score") or 0.5)
            s = level_w * 0.5 + impact * 0.3 + confidence * 0.2
            scores.append(min(1.0, s))

        if not scores:
            return None, {"source": "empty_scores", "event_count": len(events)}

        raw_score = max(scores) * 100.0
        return round(raw_score, 1), {
            "source": "event_chain",
            "event_count": len(events),
            "top_event_type": str(events[0].get("event_type") or "unknown") if events else "unknown",
            "max_impact": cls._float(events[0].get("impact_score") or 0) if events else 0,
        }

    @staticmethod
    def _apply_logic_upgrade(
        original_decision: str,
        logic_score: float,
        tier: str,
        capital_validation: str,
    ) -> str:
        """Conservative logic upgrade.

        Rules:
        - logic_score >= 70: reject → strong_branch_watch
        - logic_score >= 50: reject → strong_branch_watch (only if tier != fading)
        - NEVER upgrade to mainline_focus (requires market confirmation)
        - NEVER downgrade
        """
        # inline map so it works as static method
        if original_decision == "reject":
            target = "strong_branch_watch"
        elif original_decision == "fade_avoid":
            target = "fade_avoid"
        elif original_decision == "risk_watch":
            target = "risk_watch"
        else:
            return original_decision
        if target == original_decision:
            return original_decision
        if logic_score >= 70:
            return target
        if logic_score >= 50 and tier != "fading":
            return target
        return original_decision

    # ── P1-2: reject diagnostics ──

    @staticmethod
    def _reject_reason(decision: str, inputs: dict[str, Any]) -> str | None:
        """Return a machine-readable reject reason for rejected decisions."""
        if decision not in {"reject", "fade_avoid"}:
            return None
        reasons: list[str] = []
        if not inputs.get("alive") and float(inputs.get("mainline_strength", 0) or 0) < 50:
            reasons.append("mainline_not_alive_and_weak")
        elif float(inputs.get("fade_risk", 0) or 0) >= 70:
            reasons.append("fade_risk_high")
        elif inputs.get("tier") not in {"mainline", "strong_branch"}:
            reasons.append("tier_below_strong_branch")
        elif inputs.get("capital_validation") in {"negative", "unknown"}:
            reasons.append("capital_not_confirmed")
        else:
            reasons.append("insufficient_decision_score")
        return ";".join(reasons)

    @staticmethod
    def _check_missing_fields(
        cycle: dict[str, Any],
        capital: dict[str, Any],
        stock_facts: list[dict[str, Any]],
    ) -> list[str]:
        """Check which key fields are missing from input data sources."""
        missing: list[str] = []
        for field in ("mainline_strength_score", "fade_risk_score", "final_mainline_alive"):
            if cycle.get(field) in (None, "", 0) and field != "fade_risk_score":
                missing.append(f"cycle.{field}")
        if not cycle:
            missing.append("cycle.entire_object")
        if not capital:
            missing.append("capital.entire_object")
        elif capital.get("main_net_inflow_sum") in (None, ""):
            missing.append("capital.main_net_inflow_sum")
        if not stock_facts:
            missing.append("stock_facts.empty")
        return missing

    # ── existing helpers (unchanged logic) ──

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
        logic_score: float | None = None,
    ) -> float:
        logic_bonus = (logic_score or 0) * 0.05  # small bonus for event chain
        return round(
            mainline_score * 0.35
            + market_environment_score * 0.30
            + leader_core_score * 0.20
            + setup_plan_score * 0.15
            + logic_bonus,
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
