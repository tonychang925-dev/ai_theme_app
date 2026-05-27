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
        legacy_section_counts = self._legacy_section_counts(doc)
        diagnostics = self._build_diagnostics(doc, legacy_section_counts)
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
            "strong_stock_reviews": [],
            "watchlist_reviews": [],
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

    def _build_diagnostics(
        self,
        recap_doc: dict[str, Any],
        legacy_section_counts: dict[str, int],
    ) -> dict[str, Any]:
        source_tables = self._source_table_counts(recap_doc)
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
            coverage[module_key] = self._coverage(
                module_key=module_key,
                row_count=0,
                legacy_count=legacy_count,
                upstream_tables=source_tables,
                message=(
                    f"DailyReview V2 {module_key} structured builder is pending; "
                    f"legacy section `{heading}` count={legacy_count}."
                ),
            )

        warnings: list[str] = []
        if any(legacy_section_counts.values()):
            warnings.append("legacy sections are available but V2 structured rows are not materialized in V2-P1")
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
    ) -> dict[str, Any]:
        status = "ready" if row_count > 0 else "empty"
        if row_count > 0:
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
            "missing_fields": [],
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
