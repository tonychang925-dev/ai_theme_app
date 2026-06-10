from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from stock_processing_service.contracts.dto import PostMarketDailyReviewV2


MODULE_SECTION_HEADINGS: dict[str, str] = {
    "theme_reviews": "主线与支线",
    "theme_capital_reviews": "主线资金流入前10",
    "strong_stock_reviews": "强势股分层",
    "watchlist_reviews": "次日观察清单",
    "stock_capital_reviews": "主线股票资金流入前20",
    "abnormal_reviews": "当日异动股与资金行为",
    "money_flow_reviews": "资金行为增强",
    "dragon_tiger_reviews": "龙虎榜",
}

MODULE_KEYS: tuple[str, ...] = ("market_summary", *MODULE_SECTION_HEADINGS.keys())


class PostMarketDailyReviewV2Builder:
    """Build the DailyReview V2 view model contract without driving page rendering.

    V2-P1 intentionally emits complete module containers and diagnostics first.
    Module row materialization is introduced in later V2-P3 steps so the frontend
    cannot accidentally treat V1 arrays as V2-compatible structured rows.
    """

    schema_version = "daily_review_v2"

    def build(
        self,
        *,
        trade_date: date,
        recap_doc: dict[str, Any] | None,
        recap_snapshot_version: str | None = None,
        snapshot_id: str | None = None,
        generated_at: datetime | None = None,
        snapshot_version: str | None = None,
    ) -> PostMarketDailyReviewV2:
        doc = deepcopy(recap_doc) if isinstance(recap_doc, dict) else {}
        generated = generated_at or datetime.now(timezone.utc)
        theme_capital_reviews, theme_capital_missing_fields = self._build_theme_capital_reviews(doc)
        theme_reviews, theme_missing_fields = self._build_theme_reviews(doc, theme_capital_reviews)
        strong_stock_reviews, strong_stock_missing_fields = self._build_strong_stock_reviews(doc)
        watchlist_reviews, watchlist_missing_fields = self._build_watchlist_reviews(doc)
        stock_capital_reviews, stock_capital_missing_fields = self._build_stock_capital_reviews(doc)
        abnormal_reviews, abnormal_missing_fields = self._build_abnormal_reviews(doc)
        money_flow_reviews, money_flow_missing_fields = self._build_money_flow_reviews(doc)
        dragon_tiger_reviews, dragon_tiger_missing_fields, dragon_tiger_errors = self._build_dragon_tiger_reviews(doc)
        legacy_section_counts = self._legacy_section_counts(doc)
        diagnostics = self._build_diagnostics(
            doc,
            legacy_section_counts,
            structured_counts={
                "theme_reviews": len(theme_reviews),
                "theme_capital_reviews": len(theme_capital_reviews),
                "strong_stock_reviews": len(strong_stock_reviews),
                "watchlist_reviews": len(watchlist_reviews),
                "stock_capital_reviews": len(stock_capital_reviews),
                "abnormal_reviews": len(abnormal_reviews),
                "money_flow_reviews": len(money_flow_reviews),
                "dragon_tiger_reviews": len(dragon_tiger_reviews),
            },
            missing_fields={
                "theme_reviews": theme_missing_fields,
                "theme_capital_reviews": theme_capital_missing_fields,
                "strong_stock_reviews": strong_stock_missing_fields,
                "watchlist_reviews": watchlist_missing_fields,
                "stock_capital_reviews": stock_capital_missing_fields,
                "abnormal_reviews": abnormal_missing_fields,
                "money_flow_reviews": money_flow_missing_fields,
                "dragon_tiger_reviews": dragon_tiger_missing_fields,
            },
            errors=dragon_tiger_errors,
        )
        derived_status = self._derived_data_status(doc, diagnostics)
        recap_status = "success" if doc else "failed"
        v2_snapshot_version = snapshot_version or f"daily_review_v2.{trade_date:%Y%m%d}.{uuid4().hex[:8]}"

        return {
            "schema_version": self.schema_version,
            "trade_date": trade_date.isoformat(),
            "report_type": "post_market",
            "snapshot_version": v2_snapshot_version,
            "generated_at": generated.isoformat(),
            "data_mode": "daily_review_v2_first",
            "source": {
                "snapshot_id": snapshot_id,
                "recap_snapshot_version": recap_snapshot_version,
                "derived_data_status": derived_status,
                "recap_generate_status": recap_status,
            },
            "market_environment_review": self._market_environment_review(doc),
            "market_summary": self._market_summary(doc),
            "market_overview_review": self._pass_through_dict(doc, "market_overview_review"),
            "theme_decision_reviews": self._pass_through_list(doc, "theme_decision_reviews"),
            "theme_reviews": theme_reviews,
            "theme_capital_reviews": theme_capital_reviews,
            "strong_stock_decision_reviews": self._pass_through_list(doc, "strong_stock_decision_reviews"),
            "strong_stock_reviews": strong_stock_reviews,
            "watchlist_reviews": watchlist_reviews,
            "post_market_setup_plan": self._pass_through_dict(doc, "post_market_setup_plan"),
            "watchlists": self._pass_through_dict(doc, "watchlists"),
            "stock_capital_reviews": stock_capital_reviews,
            "abnormal_reviews": abnormal_reviews,
            "money_flow_reviews": money_flow_reviews,
            "dragon_tiger_reviews": dragon_tiger_reviews,
            "trading_principle": self._trading_principle(doc),
            "decision_diagnostics": self._pass_through_dict(doc, "decision_diagnostics"),
            "mainline_reviews": self._pass_through_list(doc, "mainline_discovery_reviews"),
            "analyst_review_items": self._pass_through_list(doc, "analyst_review_items"),
            "mainline_discovery_diagnostics": self._pass_through_dict(doc, "mainline_discovery_diagnostics"),
            "analyst_review_diagnostics": self._pass_through_dict(doc, "analyst_review_diagnostics"),
            "pending_mainline_reviews": self._pass_through_list(doc, "analyst_review_items"),
            "confirmed_mainlines": [],
            "mainline_lifecycle_reviews": self._pass_through_list(doc, "mainline_lifecycle_reviews"),
            "mainline_lifecycle_diagnostics": self._pass_through_dict(doc, "mainline_lifecycle_diagnostics"),
            "market_regime_review": self._pass_through_dict(doc, "market_regime_review"),
            "post_market_decision_v2": self._pass_through_dict(doc, "post_market_decision_v2"),
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _pass_through_list(recap_doc: dict[str, Any], key: str) -> list[Any]:
        value = recap_doc.get(key)
        return deepcopy(value) if isinstance(value, list) else []

    @staticmethod
    def _pass_through_dict(recap_doc: dict[str, Any], key: str) -> dict[str, Any]:
        value = recap_doc.get(key)
        return deepcopy(value) if isinstance(value, dict) else {}

    def _market_environment_review(self, recap_doc: dict[str, Any]) -> dict[str, Any]:
        source = recap_doc.get("market_environment_review")
        return deepcopy(source) if isinstance(source, dict) else {}

    def _market_summary(self, recap_doc: dict[str, Any]) -> dict[str, Any]:
        source = recap_doc.get("market_summary")
        if isinstance(source, dict):
            return {
                "market_bias": str(source.get("market_bias") or source.get("bias") or "unknown"),
                "action_bias": str(source.get("action_bias") or "unknown"),
                "market_health_score": source.get("market_health_score"),
                "breadth_status": source.get("breadth_status"),
                "short_term_sentiment_status": source.get("short_term_sentiment_status"),
                "relay_sentiment_status": source.get("relay_sentiment_status"),
                "intraday_fade_status": source.get("intraday_fade_status"),
                "conclusion": str(source.get("conclusion") or source.get("summary") or ""),
                "highlights": self._list(source.get("highlights")),
                "risk_flags": self._list(source.get("risk_flags")),
                "diagnostics": source.get("diagnostics") if isinstance(source.get("diagnostics"), dict) else {},
            }
        highlights = self._list(recap_doc.get("highlights"))
        return {
            "market_bias": "unknown",
            "action_bias": "unknown",
            "market_health_score": None,
            "breadth_status": None,
            "short_term_sentiment_status": None,
            "relay_sentiment_status": None,
            "intraday_fade_status": None,
            "conclusion": "",
            "highlights": highlights,
            "risk_flags": [],
            "diagnostics": {},
        }

    def _trading_principle(self, recap_doc: dict[str, Any]) -> dict[str, Any]:
        source = recap_doc.get("trading_principle")
        return deepcopy(source) if isinstance(source, dict) else {}

    def _build_theme_capital_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        source_key, source_rows = self._first_non_empty_list_source(
            recap_doc,
            (
                ("theme_capital_reviews",),
                ("report_context", "theme_capital_flow"),
                ("report_context", "capital_flow"),
            ),
        )
        if not isinstance(source_rows, list):
            return [], []

        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        for idx, source in enumerate(source_rows[:20], start=1):
            if not isinstance(source, dict):
                continue
            subject_key = self._theme_subject_key(source)
            theme_name = self._theme_name(source)
            total_inflow = self._float_or_none(
                self._first_present(source, "total_inflow", "main_net_inflow_sum", "net_inflow_sum", "main_net_inflow")
            )
            leader_inflow = self._float_or_none(
                self._first_present(source, "leader_inflow", "leader_main_net_inflow", "leader_net_inflow")
            )
            fallback_used: list[str] = []
            top3_source = self._first_present(
                source,
                "top3_inflow",
                "top3_main_net_inflow",
                "top3_main_net_inflow_sum",
                "top3_net_inflow",
            )
            top3_inflow = self._float_or_none(top3_source)
            if top3_inflow is not None and top3_source == source.get("top3_main_net_inflow_sum"):
                fallback_used.append("top3_inflow.top3_main_net_inflow_sum")
            inflow_stock_count = self._int_or_none(
                self._first_present(
                    source,
                    "inflow_stock_count",
                    "stock_count",
                    "positive_stock_count",
                    "positive_inflow_stock_count",
                    "member_count",
                )
            )
            theme_kline_source = self._first_present(
                source,
                "theme_kline",
                "kline_status",
                "theme_structure",
                "price_structure",
                "capital_focus_score",
            )
            theme_kline = self._theme_kline_text(theme_kline_source)
            if theme_kline and theme_kline_source == source.get("capital_focus_score"):
                fallback_used.append("theme_kline.capital_focus_score")
            cycle_stage = self._nullable_text(self._first_present(source, "cycle_stage", "final_cycle_state", "stage"))
            action = self._nullable_text(self._first_present(source, "action", "action_advice", "trade_action"))
            rank_order = self._int_or_none(self._first_present(source, "rank_order", "rank", "sort")) or idx
            tier = self._theme_tier(source)

            required = {
                "subject_key": subject_key,
                "theme_name": theme_name,
            }
            for field, value in required.items():
                if not value:
                    missing_fields.add(field)
            display_required = {
                "total_inflow": total_inflow is not None,
                "rank_order": rank_order is not None,
                "top3_inflow": top3_inflow is not None,
                "inflow_stock_count": inflow_stock_count is not None,
                "theme_kline": bool(theme_kline),
            }
            for field, ok in display_required.items():
                if not ok:
                    missing_fields.add(field)

            rows.append({
                "subject_key": subject_key,
                "theme_name": theme_name,
                "tier": tier,
                "total_inflow": total_inflow,
                "top3_inflow": top3_inflow,
                "leader_inflow": leader_inflow,
                "inflow_stock_count": inflow_stock_count,
                "theme_kline": theme_kline,
                "cycle_stage": cycle_stage,
                "action": action,
                "rank_order": rank_order,
                "diagnostics": {
                    "capital_row_joined": True,
                    "stock_count": inflow_stock_count or 0,
                    "source": source_key,
                    "fallback_used": fallback_used,
                    "source_tables": [source_key],
                },
            })

        return rows, sorted(missing_fields)

    def _build_theme_reviews(
        self,
        recap_doc: dict[str, Any],
        theme_capital_reviews: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        source_key, source_rows = self._first_non_empty_list_source(
            recap_doc,
            (
                ("theme_decision_reviews",),
                ("theme_reviews",),
                ("report_context", "theme_reviews"),
                ("report_context", "theme_cycle"),
                ("report_context", "theme_cycle_judgement_v2"),
                ("report_context", "cycles"),
            ),
        )
        if isinstance(source_rows, list):
            if theme_capital_reviews:
                capital_by_key = {str(row.get("subject_key") or ""): row for row in theme_capital_reviews}
                merged_rows: list[Any] = []
                for source in source_rows:
                    if not isinstance(source, dict):
                        merged_rows.append(source)
                        continue
                    capital = capital_by_key.get(self._theme_subject_key(source)) or {}
                    merged_rows.append({**capital, **source, "action": source.get("action") or capital.get("action")})
                source_rows = merged_rows
            rows, missing = self._map_theme_review_rows(source_key, source_rows)
            if rows:
                return rows, missing
        if theme_capital_reviews:
            return self._synthesize_theme_reviews_from_capital(theme_capital_reviews, recap_doc)
        return [], []

    def _map_theme_review_rows(self, source_key: str, source_rows: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        for source in source_rows[:20]:
            if not isinstance(source, dict):
                continue
            row, missing = self._theme_review_row_from_source(source, source_key)
            rows.append(row)
            missing_fields.update(missing)
        return rows, sorted(missing_fields)

    def _theme_review_row_from_source(self, source: dict[str, Any], source_key: str) -> tuple[dict[str, Any], set[str]]:
        subject_key = self._theme_subject_key(source)
        theme_name = self._theme_name(source)
        total_inflow = self._float_or_none(self._first_present(source, "total_inflow", "main_net_inflow_sum"))
        leader_inflow = self._float_or_none(self._first_present(source, "leader_inflow", "leader_main_net_inflow"))
        theme_kline = self._theme_kline_text(
            self._first_present(
                source,
                "theme_kline",
                "kline_status",
                "theme_structure",
                "final_cycle_state",
                "capital_focus_score",
            )
        )
        mainline_strength_score = self._float_or_none(
            self._first_present(source, "mainline_strength_score", "strength_score", "state_strength_score")
        )
        fallback_used: list[str] = []
        event_source = self._first_present(
            source,
            "event_score",
            "event_heat_score",
            "event_driver_score",
            "driver_score",
            "capital_focus_score",
            "mainline_strength_score",
            "strength_score",
            "state_strength_score",
        )
        event_score = self._float_or_none(event_source)
        if event_score is not None and event_source == source.get("capital_focus_score"):
            fallback_used.append("event_score.capital_focus_score")
        elif event_score is not None and event_source in {
            source.get("mainline_strength_score"),
            source.get("strength_score"),
            source.get("state_strength_score"),
        }:
            fallback_used.append("event_score.mainline_strength_score")
        market_source = self._first_present(
            source,
            "market_score",
            "market_confirmation_score",
            "mainline_strength_score",
            "strength_score",
            "state_strength_score",
        )
        market_score = self._float_or_none(market_source)
        if market_score is not None and market_source in {
            source.get("mainline_strength_score"),
            source.get("strength_score"),
            source.get("state_strength_score"),
        }:
            fallback_used.append("market_score.mainline_strength_score")
        fade_risk_score = self._float_or_none(self._first_present(source, "fade_risk_score", "fade_score"))
        cycle_stage = self._text(self._first_present(source, "cycle_stage", "final_cycle_state") or "unknown")
        final_cycle_state = self._text(self._first_present(source, "final_cycle_state", "cycle_state") or cycle_stage)
        final_mainline_alive = self._bool_or_none(
            self._first_present(source, "final_mainline_alive", "is_mainline_alive")
        )
        tier = self._theme_tier(source, final_mainline_alive=final_mainline_alive, strength_score=mainline_strength_score)
        action_source = self._nullable_text(self._first_present(source, "action_advice", "action", "trade_action"))
        conclusion_source = self._nullable_text(self._first_present(source, "conclusion", "summary", "reason"))
        decision = self._text(source.get("decision") or "")
        action_advice = self._text(
            action_source
            or source.get("action_advice")
            or self._theme_action_fallback(tier=tier, cycle_stage=cycle_stage)
        )
        if action_advice and not (action_source or source.get("action_advice")):
            fallback_used.append("action_advice")
        conclusion = self._text(
            conclusion_source
            or source.get("conclusion")
            or self._theme_conclusion_fallback(tier=tier, cycle_stage=cycle_stage)
        )
        if conclusion and not (conclusion_source or source.get("conclusion")):
            fallback_used.append("conclusion")

        missing_fields: set[str] = set()
        required = {
            "subject_key": subject_key,
            "theme_name": theme_name,
        }
        for field, value in required.items():
            if not value:
                missing_fields.add(field)
        display_required = {
            "tier": bool(tier),
            "cycle_stage_or_final_cycle_state": bool(cycle_stage or final_cycle_state),
            "action_or_conclusion": bool(action_advice or conclusion),
            "capital_or_kline": total_inflow is not None or leader_inflow is not None or bool(theme_kline),
            "event_score": event_score is not None,
            "market_score": market_score is not None,
        }
        for field, ok in display_required.items():
            if not ok:
                missing_fields.add(field)

        row = {
            "subject_key": subject_key,
            "theme_name": theme_name,
            "tier": tier,
            "total_inflow": total_inflow,
            "leader_inflow": leader_inflow,
            "theme_kline": theme_kline,
            "event_score": event_score,
            "market_score": market_score,
            "mainline_strength_score": mainline_strength_score,
            "fade_risk_score": fade_risk_score,
            "cycle_stage": cycle_stage,
            "final_cycle_state": final_cycle_state,
            "final_mainline_alive": bool(final_mainline_alive) if final_mainline_alive is not None else tier == "mainline",
            "action_advice": action_advice,
            "conclusion": conclusion,
            "decision": decision,
            "capital_validation": source.get("capital_validation"),
            "position_suggestion": self._float_or_none(source.get("position_suggestion")),
            "next_day_watch_points": self._list(source.get("next_day_watch_points")),
            "invalidation_conditions": self._list(source.get("invalidation_conditions")),
            "leader_stocks": self._list(source.get("leader_stocks")),
            "event_chain": self._list(source.get("event_chain")),
            "diagnostics": {
                "cycle_joined": True,
                "capital_joined": total_inflow is not None or leader_inflow is not None,
                "leader_count": len(self._list(source.get("leader_stocks"))),
                "source": source_key,
                "source_tables": [source_key],
                "fallback_used": fallback_used,
                "missing_fields": sorted(missing_fields),
            },
        }
        return row, missing_fields

    def _synthesize_theme_reviews_from_capital(
        self,
        theme_capital_reviews: list[dict[str, Any]],
        recap_doc: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        cycles = self._cycle_by_subject_key(recap_doc)
        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        for source in theme_capital_reviews:
            cycle = cycles.get(str(source.get("subject_key") or "")) or {}
            merged = {
                **cycle,
                **source,
                "tier": source.get("tier") or cycle.get("tier"),
                "action_advice": source.get("action") or cycle.get("action_advice") or cycle.get("action"),
                "conclusion": cycle.get("conclusion") or cycle.get("summary") or source.get("action"),
                "mainline_strength_score": cycle.get("mainline_strength_score")
                or cycle.get("strength_score")
                or source.get("total_inflow"),
                "source": "synthesized_from_theme_capital_reviews",
            }
            row, missing = self._theme_review_row_from_source(merged, "synthesized_from_theme_capital_reviews")
            row["diagnostics"]["capital_joined"] = True
            row["diagnostics"]["cycle_joined"] = bool(cycle)
            row["diagnostics"]["fallback_used"] = ["theme_reviews.from_theme_capital_reviews"]
            rows.append(row)
            missing_fields.update(missing)
        return rows, sorted(missing_fields)

    def _build_strong_stock_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        source_key, source_rows = self._first_non_empty_list_source(
            recap_doc,
            (
                ("strong_stock_decision_reviews",),
                ("strong_stock_reviews",),
                ("strong_watch_history",),
                ("promoted_pool_preview",),
                ("top_candidates",),
                ("formal_top_candidates",),
            ),
        )
        if not isinstance(source_rows, list):
            return [], []
        if source_key in {"promoted_pool_preview", "top_candidates", "formal_top_candidates"}:
            legacy_count = int(self._legacy_section_counts(recap_doc).get(MODULE_SECTION_HEADINGS["strong_stock_reviews"]) or 0)
            if legacy_count > 0:
                source_rows = source_rows[:legacy_count]
        money_by_stock = self._row_by_stock_id(self._context_rows(recap_doc, "money_flow"))
        stock_facts_by_stock = self._row_by_stock_id(self._context_rows(recap_doc, "stock_facts"))

        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        for source in source_rows:
            if not isinstance(source, dict):
                continue
            joined = self._join_stock_sources(source, money_by_stock, stock_facts_by_stock)
            stock_code = self._text(source.get("stock_code") or source.get("stock_id"))
            stock_name = self._text(source.get("stock_name"))
            subject_key = self._text(source.get("subject_key"))
            theme_name = self._text(
                self._first_present(joined, "resolved_theme_name", "subject_name", "theme_name")
            )
            raw_role = self._text(
                self._first_present(joined, "role", "role_label", "role_enhanced", "watch_status") or "unknown"
            )
            role = self._strong_role(raw_role)
            role_label = self._role_label(raw_role, role)
            composite_score = self._float_or_none(
                self._first_present(joined, "core_score", "watch_score", "candidate_score", "composite_score", "leader_composite_score")
            )
            main_net_inflow = self._float_or_none(joined.get("main_net_inflow"))
            money_flow_tier = self._nullable_text(joined.get("money_flow_tier"))
            role_enhanced = self._nullable_text(joined.get("role_enhanced"))
            support_score = self._float_or_none(joined.get("support_score"))
            support_type = self._nullable_text(joined.get("support_type"))
            position_label = self._nullable_text(joined.get("position_label"))
            pattern_labels = self._list(joined.get("pattern_labels"))
            structure_score = self._float_or_none(
                self._first_present(joined, "structure_score", "position_score", "kline_score")
            )
            rationale_source = self._nullable_text(source.get("rationale"))
            strong_grade = self._nullable_text(source.get("strong_grade"))
            llm_judgement = role_enhanced or self._nullable_text(source.get("watch_status") or source.get("candidate_level"))
            rationale = self._text(rationale_source or strong_grade or llm_judgement)
            fallback_used: list[str] = []
            support_block = source.get("support") if isinstance(source.get("support"), dict) else {}
            kline_block = source.get("kline") if isinstance(source.get("kline"), dict) else {}
            purity_score = self._float_or_none(
                self._first_present(joined, "purity_score", "theme_purity_score", "subject_purity_score", "relevance_score")
            )
            if purity_score is None:
                purity_score = self._score_from_watch_or_role(composite_score, role, default=55.0)
                fallback_used.append("purity_score.watch_score_or_role")
            leading_score = self._float_or_none(
                self._first_present(joined, "leading_score", "leader_score", "leader_composite_score", "trend_strength_score")
            )
            if leading_score is None:
                leading_score = self._score_from_role(role)
                fallback_used.append("leading_score.role")
            capital_score = self._float_or_none(
                self._first_present(joined, "capital_score", "leader_capital_score", "money_flow_score", "capital_flow_score")
            )
            if capital_score is None:
                capital_score = self._score_from_money_flow(main_net_inflow, money_flow_tier)
                if capital_score is not None:
                    fallback_used.append("capital_score.money_flow")

            required = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "role_label": role_label,
            }
            for field, value in required.items():
                if not value:
                    missing_fields.add(field)
            support_type = support_type or self._nullable_text(support_block.get("support_type"))
            support_score = support_score if support_score is not None else self._float_or_none(support_block.get("support_score"))
            if not support_type and position_label:
                support_type = position_label
                fallback_used.append("support.position_label")
            if structure_score is None:
                structure_score = support_score if support_score is not None else composite_score
                if structure_score is not None:
                    fallback_used.append("structure_score.support_or_composite")
            resilience_score = support_score if support_score is not None else composite_score
            if support_score is None and resilience_score is not None:
                fallback_used.append("resilience_score.composite_score")
            kline_position_label = position_label or self._nullable_text(kline_block.get("position_label"))
            pattern_labels = pattern_labels or [
                str(item).strip()
                for item in self._list(kline_block.get("pattern_labels"))
                if str(item).strip()
            ]
            pattern_summary = self._nullable_text(kline_block.get("pattern_summary"))
            if not kline_position_label and not pattern_labels and support_type:
                kline_position_label = support_type
                pattern_summary = support_type
                fallback_used.append("kline.support_type")
            if not pattern_labels and not pattern_summary and kline_position_label:
                pattern_summary = kline_position_label

            if role != "reject":
                display_required = {
                    "composite_score": composite_score is not None,
                    "money_flow": main_net_inflow is not None or bool(money_flow_tier),
                    "support": support_score is not None or bool(support_type),
                    "kline": bool(kline_position_label) or bool(pattern_labels),
                    "purity_score": purity_score is not None,
                    "leading_score": leading_score is not None,
                    "capital_score": capital_score is not None,
                    "rationale_or_llm_judgement": bool(rationale) or bool(llm_judgement),
                }
                for field, ok in display_required.items():
                    if not ok:
                        missing_fields.add(field)

            if rationale and not rationale_source:
                fallback_used.append("rationale")
            if llm_judgement and not role_enhanced:
                fallback_used.append("llm.judgement")
            rows.append({
                "stock_id": stock_code,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "role": role,
                "role_label": role_label or "未知",
                "candidate_level": self._candidate_level(source),
                "candidate_source": self._text(source.get("candidate_source") or f"recap_doc.{source_key}"),
                "composite_score": composite_score,
                "purity_score": purity_score,
                "leading_score": leading_score,
                "capital_score": capital_score,
                "structure_score": structure_score,
                "resilience_score": resilience_score,
                "money_flow": {
                    "main_net_inflow": main_net_inflow,
                    "money_flow_tier": money_flow_tier,
                    "role_enhanced": role_enhanced,
                },
                "kline": {
                    "position_label": kline_position_label,
                    "pattern_labels": pattern_labels,
                    "pattern_summary": pattern_summary,
                },
                "support": {
                    "support_type": support_type,
                    "support_score": support_score,
                    "support_reason": None,
                },
                "llm": {
                    "judgement": llm_judgement,
                    "reason": rationale_source,
                    "confirmation_basis": strong_grade,
                },
                "rationale": rationale,
                "rejection_reason": self._nullable_text(source.get("rejection_reason")),
                "diagnostics": {
                    "from_strong_stock_watch_history": source_key in {"strong_stock_reviews", "strong_watch_history", "promoted_pool_preview"},
                    "money_flow_joined": joined.get("main_net_inflow") is not None or bool(joined.get("money_flow_tier")),
                    "position_joined": bool(joined.get("position_label")),
                    "pattern_joined": bool(joined.get("pattern_labels")),
                    "source": f"recap_doc.{source_key}",
                    "fallback_used": fallback_used,
                    "source_tables": [f"recap_doc.{source_key}", "report_context.money_flow", "report_context.stock_facts"],
                },
            })

        return rows, sorted(missing_fields)

    def _build_stock_capital_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        source_key = "stock_capital_reviews"
        source_rows = recap_doc.get(source_key)
        if not isinstance(source_rows, list):
            context = recap_doc.get("report_context")
            context = context if isinstance(context, dict) else {}
            source_key = "report_context.money_flow"
            source_rows = context.get("money_flow")
            if not isinstance(source_rows, list):
                source_key = "report_context.money_flow_enhanced"
                source_rows = context.get("money_flow_enhanced")
        if not isinstance(source_rows, list):
            source_key = "top_candidates"
            source_rows = recap_doc.get(source_key)
        if not isinstance(source_rows, list):
            return [], []

        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        for idx, source in enumerate(source_rows[:20], start=1):
            if not isinstance(source, dict):
                continue
            stock_code = self._text(source.get("stock_code") or source.get("stock_id"))
            stock_name = self._text(source.get("stock_name"))
            subject_key = self._text(source.get("subject_key"))
            theme_name = self._text(source.get("theme_name") or source.get("subject_name") or source.get("resolved_theme_name"))
            main_net_inflow_source = source.get("main_net_inflow")
            if main_net_inflow_source in (None, ""):
                main_net_inflow_source = source.get("net_inflow")
            if main_net_inflow_source in (None, ""):
                main_net_inflow_source = source.get("net_inflow_amount")
            main_net_inflow = self._float_or_none(main_net_inflow_source)
            rank_in_theme = self._int_or_none(source.get("rank_in_theme") or source.get("main_net_inflow_rank_in_theme"))
            rank_overall = self._int_or_none(source.get("rank_overall") or source.get("rank_order")) or idx
            pct_chg = self._float_or_none(source.get("pct_chg") or source.get("change_pct"))
            turnover_rate = self._float_or_none(source.get("turnover_rate"))
            volume_ratio = self._float_or_none(source.get("volume_ratio"))
            is_leader = bool(source.get("is_leader") or source.get("leader_flag"))
            flags = [
                str(item).strip()
                for item in self._list(source.get("flags") or source.get("trigger_flags") or source.get("abnormal_labels"))
                if str(item).strip()
            ]
            if is_leader and "leader" not in {item.lower() for item in flags}:
                flags.append("leader")

            required = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
            }
            for field, value in required.items():
                if not value:
                    missing_fields.add(field)
            display_required = {
                "main_net_inflow": main_net_inflow is not None,
                "rank": rank_in_theme is not None or rank_overall is not None,
                "pct_chg_or_turnover_rate": pct_chg is not None or turnover_rate is not None,
            }
            for field, ok in display_required.items():
                if not ok:
                    missing_fields.add(field)

            rows.append({
                "stock_id": stock_code,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "main_net_inflow": main_net_inflow,
                "rank_in_theme": rank_in_theme,
                "rank_overall": rank_overall,
                "pct_chg": pct_chg,
                "turnover_rate": turnover_rate,
                "volume_ratio": volume_ratio,
                "is_leader": is_leader,
                "flags": flags,
                "diagnostics": {
                    "money_flow_joined": main_net_inflow is not None,
                    "snapshot_joined": pct_chg is not None or turnover_rate is not None or volume_ratio is not None,
                    "source": f"recap_doc.{source_key}" if not source_key.startswith("report_context.") else source_key,
                    "fallback_used": [],
                    "source_tables": [source_key],
                },
            })

        return rows, sorted(missing_fields)

    def _build_abnormal_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        source_key = "abnormal_reviews"
        source_rows = recap_doc.get(source_key)
        if not isinstance(source_rows, list):
            context = recap_doc.get("report_context")
            context = context if isinstance(context, dict) else {}
            source_key = "report_context.abnormal_signals"
            source_rows = context.get("abnormal_signals")
            if not isinstance(source_rows, list):
                source_key = "report_context.stock_abnormal_signal"
                source_rows = context.get("stock_abnormal_signal")
        if not isinstance(source_rows, list):
            return [], []

        money_by_stock = self._row_by_stock_id(self._context_rows(recap_doc, "money_flow"))
        stock_facts_by_stock = self._row_by_stock_id(self._context_rows(recap_doc, "stock_facts"))
        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        for source in source_rows[:30]:
            if not isinstance(source, dict):
                continue
            joined = self._join_stock_sources(source, money_by_stock, stock_facts_by_stock)
            stock_code = self._text(joined.get("stock_code") or joined.get("stock_id"))
            stock_name = self._text(joined.get("stock_name"))
            subject_key = self._nullable_text(joined.get("subject_key"))
            theme_name = self._nullable_text(joined.get("theme_name") or joined.get("subject_name") or joined.get("resolved_theme_name"))
            abnormal_score = self._float_or_none(
                self._first_present(joined, "abnormal_score", "abnormal_composite_score", "score", "candidate_score", "watch_score")
            )
            turnover_rate = self._float_or_none(joined.get("turnover_rate"))
            volume_ratio = self._float_or_none(
                self._first_present(joined, "volume_ratio", "vol_ratio", "amount_ratio", "volume_ratio_to_ma5", "volume_ratio_to_ma50")
            )
            fallback_used: list[str] = []
            if volume_ratio is None:
                volume_ratio = self._ratio_from_text(self._first_present(joined, "evidence", "summary", "conclusion"), "量比")
                if volume_ratio is not None:
                    fallback_used.append("volume_ratio.evidence")
            volume_vs_ma50 = self._float_or_none(joined.get("volume_vs_ma50") or joined.get("volume_ratio_to_ma50"))
            main_net_inflow = self._float_or_none(joined.get("main_net_inflow"))
            inflow_rank = self._int_or_none(joined.get("inflow_rank") or joined.get("main_net_inflow_rank_in_theme"))
            money_flow_tier = self._nullable_text(joined.get("money_flow_tier"))
            labels = [
                str(item).strip()
                for item in self._list(joined.get("labels") or joined.get("abnormal_labels") or joined.get("trigger_flags") or joined.get("signal_tags"))
                if str(item).strip()
            ]
            conclusion = self._text(joined.get("conclusion") or joined.get("abnormal_conclusion") or joined.get("reason"))
            if not labels:
                labels = self._labels_from_text(self._first_present(joined, "evidence", "summary", "conclusion"))
                if labels:
                    fallback_used.append("labels.text")

            required = {
                "stock_code": stock_code,
                "stock_name": stock_name,
            }
            for field, value in required.items():
                if not value:
                    missing_fields.add(field)
            display_required = {
                "abnormal_score": abnormal_score is not None,
                "volume_or_turnover": volume_ratio is not None or volume_vs_ma50 is not None or turnover_rate is not None,
                "labels_or_conclusion": bool(labels) or bool(conclusion),
            }
            for field, ok in display_required.items():
                if not ok:
                    missing_fields.add(field)

            rows.append({
                "stock_id": stock_code,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "abnormal_score": abnormal_score,
                "turnover_rate": turnover_rate,
                "volume_ratio": volume_ratio,
                "volume_vs_ma50": volume_vs_ma50,
                "capital": {
                    "main_net_inflow": main_net_inflow,
                    "inflow_rank": inflow_rank,
                    "money_flow_tier": money_flow_tier,
                },
                "labels": labels,
                "conclusion": conclusion,
                "diagnostics": {
                    "from_stock_abnormal_signal": source_key.endswith("stock_abnormal_signal") or source_key == "abnormal_reviews",
                    "money_flow_joined": main_net_inflow is not None or bool(money_flow_tier),
                    "theme_joined": bool(subject_key or theme_name),
                    "source": f"recap_doc.{source_key}" if not source_key.startswith("report_context.") else source_key,
                    "fallback_used": fallback_used,
                    "source_tables": [source_key],
                },
            })

        return rows, sorted(missing_fields)

    def _build_money_flow_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        source_key = "money_flow_reviews"
        source_rows = recap_doc.get(source_key)
        if not isinstance(source_rows, list):
            context = recap_doc.get("report_context")
            context = context if isinstance(context, dict) else {}
            source_key = "report_context.money_flow"
            source_rows = context.get("money_flow")
            if not isinstance(source_rows, list):
                source_key = "report_context.money_flow_enhanced"
                source_rows = context.get("money_flow_enhanced")
        if not isinstance(source_rows, list):
            return [], []

        stock_facts_by_stock = self._row_by_stock_id(self._context_rows(recap_doc, "stock_facts"))
        strong_by_stock = self._row_by_stock_id(
            recap_doc.get("strong_stock_reviews") if isinstance(recap_doc.get("strong_stock_reviews"), list) else []
        )
        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        for source in source_rows[:20]:
            if not isinstance(source, dict):
                continue
            joined = self._join_stock_sources(source, strong_by_stock, stock_facts_by_stock)
            stock_code = self._text(joined.get("stock_code") or joined.get("stock_id"))
            stock_name = self._text(joined.get("stock_name"))
            subject_key = self._text(joined.get("subject_key"))
            theme_name = self._resolved_theme_name(joined)
            main_net_inflow = self._float_or_none(
                self._first_present(joined, "main_net_inflow", "net_inflow", "net_inflow_amount")
            )
            money_flow_tier = self._nullable_text(joined.get("money_flow_tier"))
            role_enhanced = self._nullable_text(joined.get("role_enhanced"))
            institution_signal = self._nullable_text(joined.get("institution_signal"))
            hot_money_signal = self._nullable_text(joined.get("hot_money_signal"))
            dragon_tiger_signal = self._nullable_text(joined.get("dragon_tiger_signal"))
            conclusion_source = self._nullable_text(joined.get("conclusion") or joined.get("note") or joined.get("reason"))
            conclusion_fallback = self._money_flow_conclusion_fallback(
                role_enhanced=role_enhanced,
                money_flow_tier=money_flow_tier,
                institution_signal=institution_signal,
                hot_money_signal=hot_money_signal,
                dragon_tiger_signal=dragon_tiger_signal,
            )
            conclusion = self._text(conclusion_source or conclusion_fallback)
            fallback_used: list[str] = []
            kline_position = self._nullable_text(
                self._first_present(joined, "position_label", "kline_position", "support_type")
            )
            pattern_labels = [
                str(item).strip()
                for item in self._list(joined.get("pattern_labels") or joined.get("kline_pattern_labels"))
                if str(item).strip()
            ]
            pattern_summary = self._nullable_text(
                self._first_present(joined, "pattern_summary", "volume_pattern_status", "ma_alignment_status")
            )
            if not pattern_labels and not pattern_summary and money_flow_tier:
                pattern_summary = money_flow_tier
                fallback_used.append("kline.money_flow_tier")
            if not kline_position and role_enhanced:
                kline_position = role_enhanced
                fallback_used.append("kline.role_enhanced")
            if not pattern_labels and not pattern_summary and kline_position:
                pattern_summary = kline_position
                fallback_used.append("kline.position_label")

            required = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key_or_theme_name": subject_key or theme_name,
            }
            for field, value in required.items():
                if not value:
                    missing_fields.add(field)
            display_required = {
                "main_net_inflow_or_money_flow_tier": main_net_inflow is not None or bool(money_flow_tier),
                "role_or_signal": bool(role_enhanced or institution_signal or hot_money_signal),
                "conclusion": bool(conclusion),
                "kline": bool(kline_position or pattern_labels or pattern_summary),
            }
            for field, ok in display_required.items():
                if not ok:
                    missing_fields.add(field)

            if conclusion and not conclusion_source:
                fallback_used.append("conclusion")

            rows.append({
                "stock_id": stock_code,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "main_net_inflow": main_net_inflow,
                "money_flow_tier": money_flow_tier,
                "role_enhanced": role_enhanced,
                "institution_signal": institution_signal,
                "hot_money_signal": hot_money_signal,
                "dragon_tiger_signal": dragon_tiger_signal,
                "conclusion": conclusion,
                "kline": {
                    "position_label": kline_position,
                    "pattern_labels": pattern_labels,
                    "pattern_summary": pattern_summary,
                },
                "diagnostics": {
                    "from_money_flow_enhanced": source_key.endswith("money_flow_enhanced") or source_key == "money_flow_reviews",
                    "dragon_tiger_joined": bool(dragon_tiger_signal),
                    "source": f"recap_doc.{source_key}" if not source_key.startswith("report_context.") else source_key,
                    "fallback_used": fallback_used,
                    "source_tables": [source_key],
                },
            })

        return rows, sorted(missing_fields)

    def _build_dragon_tiger_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], list[str]]:
        source_key, source_rows = self._dragon_tiger_source(recap_doc)
        if not isinstance(source_rows, list):
            return [], [], []

        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        errors: list[str] = []
        legacy_count = int(self._legacy_section_counts(recap_doc).get(MODULE_SECTION_HEADINGS["dragon_tiger_reviews"]) or 0)
        source_limit = legacy_count if legacy_count > 0 else 30
        for source in source_rows[:source_limit]:
            if not isinstance(source, dict):
                continue
            if not self._dragon_tiger_source_valid(source_key, source):
                errors.append(f"dragon_tiger_reviews source rejected: {source_key}")
                continue
            stock_code = self._text(self._first_present(source, "stock_code", "stock_id", "code"))
            stock_name = self._text(self._first_present(source, "stock_name", "name"))
            subject_key = self._nullable_text(
                self._first_present(source, "subject_key", "theme_subject_key", "subject_id", "bizKey", "theme_key")
            )
            theme_name = self._nullable_text(
                self._first_present(source, "theme_name", "subject_name", "resolved_theme_name")
            )
            net_buy = self._float_or_none(
                self._first_present(source, "net_buy", "net_buy_amount", "lhb_net_buy", "net_amount")
            )
            buy_amount = self._float_or_none(
                self._first_present(source, "buy_amount", "total_buy", "lhb_buy_amount", "buy", "billboard_buy_amount")
            )
            sell_amount = self._float_or_none(
                self._first_present(source, "sell_amount", "total_sell", "lhb_sell_amount", "sell", "billboard_sell_amount")
            )
            hot_money_name = self._nullable_text(
                self._first_present(source, "hot_money_name", "famous_seat", "seat_name", "hot_money")
            )
            institution_seat_count = self._int_or_none(
                self._first_present(source, "institution_seat_count", "org_seat_count", "institution_count")
            )
            seat_type = self._seat_type(source, hot_money_name, institution_seat_count)
            reason = self._nullable_text(self._first_present(source, "reason", "lhb_reason", "list_reason"))
            continuous_days = self._int_or_none(source.get("continuous_days") or source.get("dragon_tiger_days"))
            side_summary = self._text(
                self._first_present(source, "side_summary", "summary", "conclusion")
                or self._dragon_tiger_side_summary(net_buy, buy_amount, sell_amount)
            )
            seat_summary = [
                str(item).strip()
                for item in self._dragon_tiger_seat_summary(
                    self._first_present(source, "seat_summary", "seats", "seat_details", "seat_summaries")
                )
                if str(item).strip()
            ]
            if not seat_summary and hot_money_name:
                seat_summary = [hot_money_name]

            required = {
                "stock_code": stock_code,
                "stock_name": stock_name,
            }
            for field, value in required.items():
                if not value:
                    missing_fields.add(field)
            display_required = {
                "net_buy_or_buy_sell_amount": net_buy is not None or buy_amount is not None or sell_amount is not None,
                "seat_type_or_hot_money_or_institution": seat_type != "UNKNOWN" or bool(hot_money_name) or institution_seat_count is not None,
                "reason_or_side_summary": bool(reason) or bool(side_summary),
            }
            for field, ok in display_required.items():
                if not ok:
                    missing_fields.add(field)

            rows.append({
                "stock_id": stock_code,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "net_buy": net_buy,
                "buy_amount": buy_amount,
                "sell_amount": sell_amount,
                "seat_type": seat_type,
                "hot_money_name": hot_money_name,
                "institution_seat_count": institution_seat_count,
                "reason": reason,
                "continuous_days": continuous_days,
                "side_summary": side_summary,
                "seat_summary": seat_summary,
                "diagnostics": {
                    "from_dragon_tiger_object": source_key.endswith("dragon_tiger_object") or source_key == "dragon_tiger_reviews",
                    "theme_joined": bool(subject_key or theme_name),
                    "source": f"recap_doc.{source_key}" if not source_key.startswith("report_context.") else source_key,
                    "fallback_used": [],
                    "source_tables": [source_key],
                },
            })

        return rows, sorted(missing_fields), sorted(set(errors))

    def _build_watchlist_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        source_key, source_rows = self._first_non_empty_list_source(
            recap_doc,
            (
                ("watchlist_reviews",),
                ("report_context", "watchlist_reviews"),
                ("next_day_watchlist",),
                ("watchlist",),
                ("tomorrow_watchlist",),
                ("post_market_watchlist",),
                ("observe_candidates",),
                ("report_context", "watchlist"),
                ("report_context", "observe_candidates"),
                ("report_context", "strong_stock_watch"),
                ("promoted_pool_preview",),
                ("top_candidates",),
                ("formal_top_candidates",),
            ),
        )
        synthesized = False
        if not isinstance(source_rows, list) or len(source_rows) == 0:
            strong_rows = recap_doc.get("strong_stock_reviews")
            if not isinstance(strong_rows, list):
                return [], []
            source_key = "synthesized_from_strong_stock_reviews"
            source_rows = [
                row for row in strong_rows
                if isinstance(row, dict)
                and self._strong_role(self._text(row.get("role") or row.get("watch_status") or "unknown")) != "reject"
                and self._candidate_level(row) != "reject"
            ][:20]
            synthesized = True
        else:
            source_rows = self._dedupe_stock_subject_rows(source_rows)

        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        money_by_stock = self._row_by_stock_id(self._context_rows(recap_doc, "money_flow"))
        stock_facts_by_stock = self._row_by_stock_id(self._context_rows(recap_doc, "stock_facts"))
        abnormal_by_stock = self._row_by_stock_id(
            self._context_rows(recap_doc, "abnormal_signals") or self._context_rows(recap_doc, "stock_abnormal_signal")
        )
        dragon_rows = (
            self._context_rows(recap_doc, "dragon_tiger")
            or self._context_rows(recap_doc, "dragon_tiger_object")
            or (recap_doc.get("dragon_tiger_reviews") if isinstance(recap_doc.get("dragon_tiger_reviews"), list) else [])
        )
        dragon_by_stock = self._row_by_stock_id(dragon_rows)
        for idx, source in enumerate(source_rows[:20], start=1):
            if not isinstance(source, dict):
                continue
            joined = self._join_stock_sources(source, money_by_stock, stock_facts_by_stock)
            joined = self._merge_stock_source(joined, abnormal_by_stock)
            joined = self._merge_stock_source(joined, dragon_by_stock, overwrite=False)
            stock_code = self._text(joined.get("stock_code") or joined.get("stock_id"))
            stock_name = self._text(joined.get("stock_name"))
            subject_key = self._text(joined.get("subject_key"))
            theme_name = self._text(
                self._first_present(joined, "theme_name", "subject_name", "resolved_theme_name")
            )
            category = self._watchlist_category(source)
            role_label = self._text(
                joined.get("role_label")
                or joined.get("role")
                or joined.get("role_enhanced")
                or joined.get("watch_status")
                or joined.get("candidate_level")
                or "观察"
            )
            stage = self._nullable_text(
                joined.get("stage")
                or joined.get("cycle_stage")
                or joined.get("final_cycle_state")
                or joined.get("cycle_state")
            )
            action = self._nullable_text(joined.get("action") or "观察竞价承接")
            fallback_used = ["watchlist.from_strong_stock_reviews"] if synthesized else []
            volume_ratio = self._float_or_none(
                self._first_present(joined, "volume_ratio", "vol_ratio", "amount_ratio", "volume_ratio_to_ma5")
            )
            if volume_ratio is None:
                volume_ratio = self._ratio_from_text(self._first_present(joined, "evidence", "summary", "reason"), "量比")
                if volume_ratio is not None:
                    fallback_used.append("volume_ratio.evidence")
            pattern = self._nullable_text(
                joined.get("pattern")
                or joined.get("pattern_summary")
                or joined.get("position_label")
                or joined.get("support_type")
            )
            pattern_label_list = self._list(joined.get("pattern_labels"))
            if not pattern and pattern_label_list:
                pattern = "/".join(str(item).strip() for item in pattern_label_list if str(item).strip())
                fallback_used.append("pattern.pattern_labels")
            if not pattern:
                pattern = stage or role_label or category
                fallback_used.append("pattern.stage_or_role")
            flags = [
                str(item).strip()
                for item in self._list(
                    joined.get("flags")
                    or joined.get("trigger_flags")
                    or joined.get("evidence_rules")
                    or joined.get("abnormal_labels")
                    or joined.get("labels")
                )
                if str(item).strip()
            ]
            if not flags:
                flags = self._labels_from_text(self._first_present(joined, "evidence", "summary", "reason"))
                if flags:
                    fallback_used.append("flags.text")
            for label_source, prefix in (("prior7_limitup_days", "7日涨停"), ("recent_limit_up_count", "近期涨停")):
                value = self._int_or_none(joined.get(label_source))
                if value and all(not item.startswith(prefix) for item in flags):
                    flags.append(f"{prefix}{value}")
            dragon_tiger_days = self._int_or_none(
                joined.get("dragon_tiger_days")
                or joined.get("dragon_tiger_recent_days")
                or joined.get("dragon_tiger_days_7d")
                or joined.get("continuous_days")
            )
            if dragon_tiger_days is None and self._stock_key(stock_code) in dragon_by_stock:
                dragon_tiger_days = 1
                fallback_used.append("dragon_tiger_days.joined")
            if dragon_tiger_days is None:
                dragon_tiger_days = 0
                fallback_used.append("dragon_tiger_days.default_zero")
            catalyst = self._nullable_text(joined.get("catalyst") or joined.get("event_title") or joined.get("support_type"))
            abnormal_labels = [
                str(item).strip()
                for item in self._list(joined.get("abnormal_labels") or joined.get("labels"))
                if str(item).strip()
            ]
            priority = self._int_or_none(joined.get("priority") or joined.get("candidate_rank")) or idx
            reason = self._text(
                joined.get("reason")
                or joined.get("rationale")
                or joined.get("selected_reason")
                or joined.get("watch_reason")
                or joined.get("strong_grade")
                or joined.get("role_enhanced")
                or "；".join(flags[:3])
                or catalyst
                or (
                    f"{role_label} / {pattern or stage or action or category}"
                    if source_key in {"promoted_pool_preview", "top_candidates", "formal_top_candidates"}
                    else ""
                )
            )

            required = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "category": category,
            }
            for field, value in required.items():
                if not value:
                    missing_fields.add(field)
            display_required = {
                "role_label": bool(role_label),
                "stage_or_action": bool(stage) or bool(action),
                "volume_ratio": volume_ratio is not None,
                "pattern": bool(pattern),
                "flags": bool(flags),
                "dragon_tiger_days": dragon_tiger_days is not None,
                "reason": bool(reason),
                "priority": priority is not None,
            }
            for field, ok in display_required.items():
                if not ok:
                    missing_fields.add(field)

            rows.append({
                "stock_id": stock_code,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "subject_key": subject_key,
                "theme_name": theme_name,
                "category": category,
                "role_label": role_label,
                "stage": stage,
                "action": action,
                "buy_condition": self._list(source.get("buy_condition")),
                "invalid_condition": self._list(source.get("invalid_condition")),
                "risk_level": self._nullable_text(source.get("risk_level")),
                "suggested_position": self._float_or_none(source.get("suggested_position")),
                "volume_ratio": volume_ratio,
                "pattern": pattern,
                "flags": flags,
                "dragon_tiger_days": dragon_tiger_days,
                "catalyst": catalyst,
                "abnormal_labels": abnormal_labels,
                "priority": priority,
                "reason": reason,
                "diagnostics": {
                    "source": source_key if source_key.startswith(("report_context.", "synthesized_")) else f"recap_doc.{source_key}",
                    "fallback_used": fallback_used,
                    "source_tables": [source_key],
                },
            })

        return rows, sorted(missing_fields)

    @classmethod
    def _dedupe_stock_subject_rows(cls, rows: list[Any]) -> list[Any]:
        deduped: list[Any] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            if not isinstance(row, dict):
                deduped.append(row)
                continue
            stock_key = cls._stock_key(row.get("stock_id") or row.get("stock_code") or row.get("code"))
            subject_key = str(
                row.get("subject_key")
                or row.get("theme_key")
                or row.get("subject_name")
                or row.get("theme_name")
                or ""
            ).strip()
            dedupe_key = (stock_key, subject_key)
            if stock_key and dedupe_key in seen:
                continue
            if stock_key:
                seen.add(dedupe_key)
            deduped.append(row)
        return deduped

    def _build_diagnostics(
        self,
        recap_doc: dict[str, Any],
        legacy_section_counts: dict[str, int],
        structured_counts: dict[str, int] | None = None,
        missing_fields: dict[str, list[str]] | None = None,
        errors: list[str] | None = None,
    ) -> dict[str, Any]:
        source_tables = self._source_table_counts(recap_doc)
        structured_counts = structured_counts or {}
        missing_fields = missing_fields or {}
        coverage: dict[str, dict[str, Any]] = {}
        coverage["market_summary"] = self._coverage(
            module_key="market_summary",
            row_count=1 if bool(recap_doc.get("market_summary")) else 0,
            legacy_count=0,
            upstream_tables=source_tables,
            message="DailyReview V2 market_summary builder skeleton is available.",
        )
        for module_key, heading in MODULE_SECTION_HEADINGS.items():
            legacy_count = int(legacy_section_counts.get(heading) or 0)
            row_count = int(structured_counts.get(module_key) or 0)
            module_missing = list(missing_fields.get(module_key) or [])
            message = (
                f"DailyReview V2 {module_key} structured rows={row_count}; "
                f"legacy section `{heading}` count={legacy_count}."
            )
            if module_key == "dragon_tiger_reviews":
                if row_count == 0 and legacy_count == 0:
                    message = "no_dragon_tiger_day"
                elif row_count == 0 and legacy_count > 0:
                    message = "structured dragon_tiger_reviews unavailable; fallback to legacy section"
            coverage[module_key] = self._coverage(
                module_key=module_key,
                row_count=row_count,
                legacy_count=legacy_count,
                missing_fields=module_missing,
                upstream_tables=source_tables,
                message=message,
            )

        warnings: list[str] = []
        if any(legacy_section_counts.values()):
            warnings.append("legacy sections are available; modules without ready structured rows should fallback to legacy sections")
        if not recap_doc:
            warnings.append("post_market_recap_snapshot is missing or empty")

        return {
            "module_coverage": coverage,
            "column_missing_fields": {
                module_key: sorted(list(fields))
                for module_key, fields in missing_fields.items()
            },
            "source_tables": source_tables,
            "warnings": warnings,
            "errors": (errors or []) if recap_doc else ["post_market_recap_snapshot_missing", *(errors or [])],
            "legacy_sections_available": any(count > 0 for count in legacy_section_counts.values()),
            "legacy_section_counts": legacy_section_counts,
        }

    def _coverage(
        self,
        *,
        module_key: str,
        row_count: int,
        legacy_count: int,
        upstream_tables: dict[str, int],
        message: str,
        missing_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        missing_fields = missing_fields or []
        status = "ready" if row_count > 0 and not missing_fields else "partial" if row_count > 0 else "empty"
        if row_count > 0 and not missing_fields:
            source = "structured"
        elif legacy_count > 0:
            source = "legacy_sections"
        else:
            source = "none"
        return {
            "status": status,
            "row_count": row_count,
            "required": module_key in MODULE_KEYS,
            "source": source,
            "missing_fields": missing_fields,
            "column_missing_fields": missing_fields,
            "upstream_tables": upstream_tables,
            "message": message,
            "legacy_row_count": legacy_count,
        }

    def _legacy_section_counts(self, recap_doc: dict[str, Any]) -> dict[str, int]:
        counts = {heading: 0 for heading in MODULE_SECTION_HEADINGS.values()}
        report = recap_doc.get("report")
        sections = report.get("sections") if isinstance(report, dict) else None
        if not isinstance(sections, list):
            return counts
        for section in sections:
            if not isinstance(section, dict):
                continue
            heading = str(section.get("heading") or section.get("title") or "")
            items = section.get("items")
            if heading in counts and isinstance(items, list):
                counts[heading] = len(items)
        return counts

    def _source_table_counts(self, recap_doc: dict[str, Any]) -> dict[str, int]:
        context = recap_doc.get("report_context")
        if not isinstance(context, dict):
            return {}
        counts: dict[str, int] = {}
        for key, value in context.items():
            if isinstance(value, list):
                counts[key] = len(value)
            elif isinstance(value, dict):
                rows = value.get("rows")
                counts[key] = len(rows) if isinstance(rows, list) else len(value)
            elif value is None:
                counts[key] = 0
            else:
                counts[key] = 1
        return counts

    def _derived_data_status(self, recap_doc: dict[str, Any], diagnostics: dict[str, Any]) -> str:
        readiness = recap_doc.get("diagnostics", {}).get("readiness") if isinstance(recap_doc.get("diagnostics"), dict) else None
        if isinstance(readiness, dict):
            status = str(readiness.get("status") or "").lower()
            if status == "ready":
                return "ready"
            if status in {"partial", "failed_precondition"}:
                return status
        if diagnostics.get("source_tables"):
            return "partial"
        return "failed_precondition"

    @staticmethod
    def _list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return deepcopy(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return parsed
                except (TypeError, ValueError):
                    pass
            return [part.strip() for part in text.replace("；", ",").replace("/", ",").split(",") if part.strip()]
        return []

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _nullable_text(cls, value: Any) -> str | None:
        text = cls._text(value)
        return text or None

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _first_present(source: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = source.get(key)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _first_list_source(
        cls,
        recap_doc: dict[str, Any],
        paths: tuple[tuple[str, ...], ...],
    ) -> tuple[str, list[Any] | None]:
        for path in paths:
            current: Any = recap_doc
            for key in path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(key)
            if isinstance(current, list):
                return ".".join(path), current
        return "", None

    @classmethod
    def _first_non_empty_list_source(
        cls,
        recap_doc: dict[str, Any],
        paths: tuple[tuple[str, ...], ...],
    ) -> tuple[str, list[Any] | None]:
        fallback_key = ""
        fallback_rows: list[Any] | None = None
        for path in paths:
            current: Any = recap_doc
            for key in path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(key)
            if isinstance(current, list):
                if current:
                    return ".".join(path), current
                if fallback_rows is None:
                    fallback_key = ".".join(path)
                    fallback_rows = current
        return fallback_key, fallback_rows

    @staticmethod
    def _stock_key(value: Any) -> str:
        text = str(value or "").strip().upper()
        if "." in text:
            text = text.split(".", 1)[0]
        return text

    @classmethod
    def _row_by_stock_id(cls, rows: list[Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = cls._stock_key(row.get("stock_id") or row.get("stock_code") or row.get("code"))
            if key and key not in result:
                result[key] = row
        return result

    @staticmethod
    def _context_rows(recap_doc: dict[str, Any], key: str) -> list[Any]:
        context = recap_doc.get("report_context")
        if not isinstance(context, dict):
            return []
        rows = context.get(key)
        return rows if isinstance(rows, list) else []

    @classmethod
    def _join_stock_sources(
        cls,
        source: dict[str, Any],
        money_by_stock: dict[str, dict[str, Any]],
        stock_facts_by_stock: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        key = cls._stock_key(source.get("stock_id") or source.get("stock_code") or source.get("code"))
        joined: dict[str, Any] = {}
        if key and key in stock_facts_by_stock:
            joined.update(stock_facts_by_stock[key])
        if key and key in money_by_stock:
            joined.update(money_by_stock[key])
        joined.update(source)
        return joined

    @classmethod
    def _merge_stock_source(
        cls,
        source: dict[str, Any],
        rows_by_stock: dict[str, dict[str, Any]],
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        key = cls._stock_key(source.get("stock_id") or source.get("stock_code") or source.get("code"))
        extra = rows_by_stock.get(key) if key else None
        if not extra:
            return source
        merged = dict(source)
        for field, value in extra.items():
            if value in (None, ""):
                continue
            if overwrite or merged.get(field) in (None, "", []):
                merged[field] = value
        return merged

    @staticmethod
    def _score_from_role(role: str) -> float | None:
        scores = {
            "leader": 85.0,
            "sub_leader": 75.0,
            "trend": 65.0,
            "watch": 55.0,
            "observe_only": 45.0,
            "reject": 0.0,
            "unknown": 50.0,
        }
        return scores.get(role)

    @classmethod
    def _score_from_watch_or_role(cls, watch_score: float | None, role: str, *, default: float) -> float:
        if watch_score is not None:
            return max(0.0, min(100.0, watch_score))
        return cls._score_from_role(role) or default

    @staticmethod
    def _score_from_money_flow(main_net_inflow: float | None, money_flow_tier: str | None) -> float | None:
        tier = str(money_flow_tier or "").strip().lower()
        if tier in {"strong", "high", "强", "强势", "high_inflow"}:
            return 85.0
        if tier in {"mid", "medium", "normal", "中", "中等"}:
            return 65.0
        if tier in {"weak", "low", "弱"}:
            return 45.0
        if main_net_inflow is None:
            return None
        if main_net_inflow >= 100_000_000:
            return 85.0
        if main_net_inflow >= 30_000_000:
            return 70.0
        if main_net_inflow > 0:
            return 55.0
        return 40.0

    @classmethod
    def _ratio_from_text(cls, value: Any, label: str) -> float | None:
        values = cls._list(value)
        if not values and value not in (None, ""):
            values = [str(value)]
        for item in values:
            text = str(item)
            if label not in text:
                continue
            tail = text.split(label, 1)[1].strip(" ：:=倍xX")
            token = ""
            for char in tail:
                if char.isdigit() or char in ".-":
                    token += char
                elif token:
                    break
            parsed = cls._float_or_none(token)
            if parsed is not None:
                return parsed
        return None

    @classmethod
    def _labels_from_text(cls, value: Any) -> list[str]:
        labels: list[str] = []
        for item in cls._list(value):
            text = str(item).strip()
            if not text:
                continue
            head = text.split("：", 1)[0].split(":", 1)[0].strip()
            if head and len(head) <= 12:
                labels.append(head)
        return labels[:6]

    @classmethod
    def _theme_subject_key(cls, source: dict[str, Any]) -> str:
        return cls._text(
            cls._first_present(source, "subject_key", "theme_subject_key", "subject_id", "bizKey", "theme_key")
        )

    @classmethod
    def _theme_name(cls, source: dict[str, Any]) -> str:
        return cls._text(cls._first_present(source, "theme_name", "subject_name", "name"))

    @classmethod
    def _resolved_theme_name(cls, source: dict[str, Any]) -> str:
        for key in ("resolved_theme_name", "subject_name", "theme_display_name", "theme_cn_name", "name"):
            text = cls._text(source.get(key))
            if text and not text.isdigit():
                return text
        theme_name = cls._text(source.get("theme_name"))
        if theme_name and not theme_name.isdigit():
            return theme_name
        return cls._text(source.get("subject_key") or theme_name)

    @classmethod
    def _theme_kline_text(cls, value: Any) -> str | None:
        score = cls._float_or_none(value)
        if score is not None:
            return f"强度 {score:.2f}"
        return cls._nullable_text(value)

    @classmethod
    def _theme_tier(
        cls,
        source: dict[str, Any],
        *,
        final_mainline_alive: bool | None = None,
        strength_score: float | None = None,
    ) -> str:
        raw = cls._text(cls._first_present(source, "tier", "theme_tier", "mainline_level"))
        normalized = raw.lower()
        if normalized in {"mainline", "main", "主线"}:
            return "mainline"
        if normalized in {"strong_branch", "branch", "强分支"}:
            return "strong_branch"
        if normalized in {"fading", "fade", "退潮"}:
            return "fading"
        if final_mainline_alive is None:
            final_mainline_alive = cls._bool_or_none(cls._first_present(source, "final_mainline_alive", "is_mainline_alive"))
        if strength_score is None:
            strength_score = cls._float_or_none(cls._first_present(source, "mainline_strength_score", "strength_score"))
        if final_mainline_alive is True:
            return "mainline"
        if strength_score is not None and strength_score >= 60:
            return "mainline"
        if normalized in {"watch", "观察"}:
            return "watch"
        return "watch"

    @staticmethod
    def _bool_or_none(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if value is None or value == "":
            return None
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y", "是"}:
            return True
        if text in {"false", "0", "no", "n", "否"}:
            return False
        return None

    def _cycle_by_subject_key(self, recap_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
        context = recap_doc.get("report_context")
        context = context if isinstance(context, dict) else {}
        rows = (
            context.get("theme_cycle_judgement_v2")
            or context.get("theme_cycle")
            or context.get("cycles")
            or []
        )
        result: dict[str, dict[str, Any]] = {}
        if not isinstance(rows, list):
            return result
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = self._theme_subject_key(row)
            if key:
                result[key] = row
        return result

    @classmethod
    def _dragon_tiger_source(cls, recap_doc: dict[str, Any]) -> tuple[str, list[Any] | None]:
        source_key, rows = cls._first_list_source(
            recap_doc,
            (
                ("dragon_tiger_reviews",),
                ("report_context", "dragon_tiger"),
                ("report_context", "dragon_tiger_object"),
                ("dragon_tiger_object",),
            ),
        )
        if isinstance(rows, list):
            return source_key, rows

        capital_rows = recap_doc.get("capital_reviews")
        if isinstance(capital_rows, list) and any(
            isinstance(row, dict) and cls._dragon_tiger_row_has_indicator(row)
            for row in capital_rows
        ):
            return "capital_reviews", capital_rows
        return "", None

    @classmethod
    def _dragon_tiger_source_valid(cls, source_key: str, row: dict[str, Any]) -> bool:
        if source_key in {
            "dragon_tiger_reviews",
            "report_context.dragon_tiger",
            "report_context.dragon_tiger_object",
            "dragon_tiger_object",
        }:
            return True
        if source_key == "capital_reviews":
            return cls._dragon_tiger_row_has_indicator(row)
        return False

    @classmethod
    def _dragon_tiger_row_has_indicator(cls, row: dict[str, Any]) -> bool:
        key_groups = (
            ("seat_type", "seat_category", "trader_type", "hot_money_name", "famous_seat", "seat_name", "hot_money", "institution_seat_count", "org_seat_count", "institution_count"),
            ("net_buy", "net_buy_amount", "lhb_net_buy", "net_amount", "buy_amount", "total_buy", "lhb_buy_amount", "buy", "billboard_buy_amount", "sell_amount", "total_sell", "lhb_sell_amount", "sell", "billboard_sell_amount"),
        )
        for keys in key_groups:
            if any(row.get(key) not in (None, "") for key in keys):
                return True
        reason = cls._text(cls._first_present(row, "reason", "lhb_reason", "list_reason"))
        return any(token in reason for token in ("龙虎榜", "机构席位", "游资席位"))

    @staticmethod
    def _dragon_tiger_seat_summary(value: Any) -> list[Any]:
        if isinstance(value, list):
            return deepcopy(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("[") and text.endswith("]"):
                try:
                    import json

                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return parsed
                except (TypeError, ValueError):
                    pass
            return [text]
        return []

    @staticmethod
    def _seat_type(source: dict[str, Any], hot_money_name: str | None, institution_seat_count: int | None) -> str:
        text = str(source.get("seat_type") or source.get("seat_category") or source.get("trader_type") or "").upper()
        if text in {"INSTITUTION", "HOT_MONEY", "MIXED", "UNKNOWN"}:
            return text
        raw = str(source.get("seat_type") or source.get("seat_category") or source.get("trader_type") or source.get("seat_name") or "")
        if institution_seat_count and institution_seat_count > 0 and hot_money_name:
            return "MIXED"
        if institution_seat_count and institution_seat_count > 0:
            return "INSTITUTION"
        if hot_money_name or "游资" in raw:
            return "HOT_MONEY"
        if "机构" in raw:
            return "INSTITUTION"
        return "UNKNOWN"

    @staticmethod
    def _dragon_tiger_side_summary(net_buy: float | None, buy_amount: float | None, sell_amount: float | None) -> str:
        if net_buy is not None:
            return f"净买 {net_buy:.0f}"
        if buy_amount is not None or sell_amount is not None:
            buy_text = f"买 {buy_amount:.0f}" if buy_amount is not None else "买 --"
            sell_text = f"卖 {sell_amount:.0f}" if sell_amount is not None else "卖 --"
            return f"{buy_text} / {sell_text}"
        return ""

    @staticmethod
    def _money_flow_conclusion_fallback(
        *,
        role_enhanced: str | None,
        money_flow_tier: str | None,
        institution_signal: str | None,
        hot_money_signal: str | None,
        dragon_tiger_signal: str | None,
    ) -> str:
        role_parts = [part for part in (role_enhanced, money_flow_tier) if part]
        if role_parts:
            return " / ".join(role_parts)
        for signal in (institution_signal, hot_money_signal, dragon_tiger_signal):
            if signal:
                return signal
        return ""

    @staticmethod
    def _theme_action_fallback(*, tier: str, cycle_stage: str) -> str:
        if tier == "mainline":
            return f"围绕{cycle_stage or '当前'}阶段观察分歧承接"
        if tier == "strong_branch":
            return f"按{cycle_stage or '当前'}阶段控制仓位参与"
        return f"保持观察，等待{cycle_stage or '周期'}确认"

    @staticmethod
    def _theme_conclusion_fallback(*, tier: str, cycle_stage: str) -> str:
        tier_text = {
            "mainline": "主线",
            "strong_branch": "强分支",
            "watch": "观察题材",
            "fading": "退潮题材",
        }.get(tier, "题材")
        return f"{tier_text}处于{cycle_stage or '未知'}阶段"

    @staticmethod
    def _strong_role(value: str) -> str:
        text = value.lower()
        if "leader" in text or "龙头" in value:
            return "leader"
        if "sub" in text or "龙二" in value or "卡位" in value:
            return "sub_leader"
        if "trend" in text or "趋势" in value:
            return "trend"
        if "observe" in text or "观察" in value:
            return "observe_only"
        if "reject" in text or "淘汰" in value:
            return "reject"
        if text and text != "unknown":
            return "watch"
        return "unknown"

    @staticmethod
    def _role_label(raw_role: str, role: str) -> str:
        if raw_role and raw_role != "unknown":
            return raw_role
        labels = {
            "leader": "龙头",
            "sub_leader": "龙二/卡位",
            "trend": "趋势",
            "watch": "观察",
            "observe_only": "仅观察",
            "reject": "淘汰",
            "unknown": "未知",
        }
        return labels.get(role, "未知")

    @staticmethod
    def _candidate_level(source: dict[str, Any]) -> str:
        text = str(source.get("candidate_level") or source.get("watch_status") or source.get("role") or "").lower()
        if "reject" in text or "淘汰" in text:
            return "reject"
        if "observe" in text or "观察" in text:
            return "observe_only"
        if text:
            return "formal"
        return "unknown"

    @staticmethod
    def _watchlist_category(source: dict[str, Any]) -> str:
        text = str(
            source.get("category")
            or source.get("candidate_level")
            or source.get("watch_status")
            or source.get("pool_entry_type")
            or ""
        )
        lower = text.lower()
        if "risk" in lower or "风险" in text:
            return "风险观察"
        if "weak" in lower or "rebound" in lower or "弱转强" in text:
            return "弱转强观察"
        if "observe" in lower or "观察" in text:
            return "重点观察"
        if text:
            return "其他"
        return "其他"
