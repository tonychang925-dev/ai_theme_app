from __future__ import annotations

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
        strong_stock_reviews, strong_stock_missing_fields = self._build_strong_stock_reviews(doc)
        watchlist_reviews, watchlist_missing_fields = self._build_watchlist_reviews(doc)
        legacy_section_counts = self._legacy_section_counts(doc)
        diagnostics = self._build_diagnostics(
            doc,
            legacy_section_counts,
            structured_counts={
                "strong_stock_reviews": len(strong_stock_reviews),
                "watchlist_reviews": len(watchlist_reviews),
            },
            missing_fields={
                "strong_stock_reviews": strong_stock_missing_fields,
                "watchlist_reviews": watchlist_missing_fields,
            },
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
            "market_summary": self._market_summary(doc),
            "theme_reviews": [],
            "theme_capital_reviews": [],
            "strong_stock_reviews": strong_stock_reviews,
            "watchlist_reviews": watchlist_reviews,
            "stock_capital_reviews": [],
            "abnormal_reviews": [],
            "money_flow_reviews": [],
            "dragon_tiger_reviews": [],
            "trading_principle": self._trading_principle(doc),
            "diagnostics": diagnostics,
        }

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

    def _build_strong_stock_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        source_rows = recap_doc.get("strong_stock_reviews")
        if not isinstance(source_rows, list):
            return [], []

        rows: list[dict[str, Any]] = []
        missing_fields: set[str] = set()
        for source in source_rows:
            if not isinstance(source, dict):
                continue
            stock_code = self._text(source.get("stock_code") or source.get("stock_id"))
            stock_name = self._text(source.get("stock_name"))
            subject_key = self._text(source.get("subject_key"))
            theme_name = self._text(source.get("theme_name"))
            raw_role = self._text(source.get("role") or source.get("watch_status") or "unknown")
            role = self._strong_role(raw_role)
            role_label = self._role_label(raw_role, role)
            composite_score = self._float_or_none(source.get("watch_score"))
            main_net_inflow = self._float_or_none(source.get("main_net_inflow"))
            money_flow_tier = self._nullable_text(source.get("money_flow_tier"))
            role_enhanced = self._nullable_text(source.get("role_enhanced"))
            support_score = self._float_or_none(source.get("support_score"))
            support_type = self._nullable_text(source.get("support_type"))
            position_label = self._nullable_text(source.get("position_label"))
            pattern_labels = self._list(source.get("pattern_labels"))
            rationale_source = self._nullable_text(source.get("rationale"))
            strong_grade = self._nullable_text(source.get("strong_grade"))
            llm_judgement = role_enhanced or self._nullable_text(source.get("watch_status"))
            rationale = self._text(rationale_source or strong_grade or llm_judgement)

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
            display_required = {
                "composite_score": composite_score is not None,
                "money_flow": main_net_inflow is not None or bool(money_flow_tier),
                "support": support_score is not None or bool(support_type),
                "kline": bool(position_label) or bool(pattern_labels),
                "rationale_or_llm_judgement": bool(rationale) or bool(llm_judgement),
            }
            for field, ok in display_required.items():
                if not ok:
                    missing_fields.add(field)

            fallback_used: list[str] = []
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
                "candidate_source": self._text(source.get("candidate_source") or "recap_doc.strong_stock_reviews"),
                "composite_score": composite_score,
                "purity_score": None,
                "leading_score": None,
                "capital_score": None,
                "structure_score": None,
                "resilience_score": support_score,
                "money_flow": {
                    "main_net_inflow": main_net_inflow,
                    "money_flow_tier": money_flow_tier,
                    "role_enhanced": role_enhanced,
                },
                "kline": {
                    "position_label": position_label,
                    "pattern_labels": pattern_labels,
                    "pattern_summary": None,
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
                    "from_strong_stock_watch_history": True,
                    "money_flow_joined": source.get("main_net_inflow") is not None or bool(source.get("money_flow_tier")),
                    "position_joined": bool(source.get("position_label")),
                    "pattern_joined": bool(source.get("pattern_labels")),
                    "source": "recap_doc.strong_stock_reviews",
                    "fallback_used": fallback_used,
                    "source_tables": ["recap_doc.strong_stock_reviews"],
                },
            })

        return rows, sorted(missing_fields)

    def _build_watchlist_reviews(self, recap_doc: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        source_key = "watchlist_reviews"
        source_rows = recap_doc.get(source_key)
        if not isinstance(source_rows, list):
            source_key = "observe_candidates"
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
            theme_name = self._text(source.get("theme_name") or source.get("subject_name"))
            category = self._watchlist_category(source)
            role_label = self._text(
                source.get("role_label")
                or source.get("role")
                or source.get("watch_status")
                or source.get("candidate_level")
                or "观察"
            )
            stage = self._nullable_text(
                source.get("stage")
                or source.get("cycle_stage")
                or source.get("final_cycle_state")
                or source.get("cycle_state")
            )
            action = self._nullable_text(source.get("action") or "观察竞价承接")
            volume_ratio = self._float_or_none(source.get("volume_ratio"))
            pattern = self._nullable_text(
                source.get("pattern")
                or source.get("pattern_summary")
                or source.get("position_label")
                or source.get("support_type")
            )
            flags = [
                str(item).strip()
                for item in self._list(source.get("flags") or source.get("trigger_flags") or source.get("evidence_rules"))
                if str(item).strip()
            ]
            dragon_tiger_days = self._int_or_none(
                source.get("dragon_tiger_days")
                or source.get("dragon_tiger_recent_days")
                or source.get("dragon_tiger_days_7d")
            )
            catalyst = self._nullable_text(source.get("catalyst") or source.get("event_title") or source.get("support_type"))
            abnormal_labels = [
                str(item).strip()
                for item in self._list(source.get("abnormal_labels") or source.get("labels"))
                if str(item).strip()
            ]
            priority = self._int_or_none(source.get("priority") or source.get("candidate_rank")) or idx
            reason = self._text(
                source.get("reason")
                or source.get("rationale")
                or source.get("selected_reason")
                or source.get("watch_reason")
                or "；".join(flags[:3])
                or catalyst
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
                "volume_ratio": volume_ratio,
                "pattern": pattern,
                "flags": flags,
                "dragon_tiger_days": dragon_tiger_days,
                "catalyst": catalyst,
                "abnormal_labels": abnormal_labels,
                "priority": priority,
                "reason": reason,
                "diagnostics": {
                    "source": f"recap_doc.{source_key}",
                    "fallback_used": [],
                    "source_tables": [f"recap_doc.{source_key}"],
                },
            })

        return rows, sorted(missing_fields)

    def _build_diagnostics(
        self,
        recap_doc: dict[str, Any],
        legacy_section_counts: dict[str, int],
        structured_counts: dict[str, int] | None = None,
        missing_fields: dict[str, list[str]] | None = None,
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
            coverage[module_key] = self._coverage(
                module_key=module_key,
                row_count=row_count,
                legacy_count=legacy_count,
                missing_fields=module_missing,
                upstream_tables=source_tables,
                message=(
                    f"DailyReview V2 {module_key} structured rows={row_count}; "
                    f"legacy section `{heading}` count={legacy_count}."
                ),
            )

        warnings: list[str] = []
        if any(legacy_section_counts.values()):
            warnings.append("legacy sections are available; modules without ready structured rows should fallback to legacy sections")
        if not recap_doc:
            warnings.append("post_market_recap_snapshot is missing or empty")

        return {
            "module_coverage": coverage,
            "source_tables": source_tables,
            "warnings": warnings,
            "errors": [] if recap_doc else ["post_market_recap_snapshot_missing"],
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
        return deepcopy(value) if isinstance(value, list) else []

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
