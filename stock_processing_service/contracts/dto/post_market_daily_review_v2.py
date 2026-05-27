from __future__ import annotations

from typing import Any, Literal, TypedDict


class ModuleCoverage(TypedDict, total=False):
    status: Literal["ready", "empty", "partial", "failed"]
    row_count: int
    required: bool
    source: Literal["structured", "legacy_sections", "none"]
    missing_fields: list[str]
    upstream_tables: dict[str, int]
    message: str
    legacy_row_count: int


class DailyReviewDiagnostics(TypedDict):
    module_coverage: dict[str, ModuleCoverage]
    source_tables: dict[str, int]
    warnings: list[str]
    errors: list[str]
    legacy_sections_available: bool
    legacy_section_counts: dict[str, int]


class PostMarketDailyReviewV2(TypedDict):
    schema_version: Literal["daily_review_v2"]
    trade_date: str
    report_type: Literal["post_market"]
    snapshot_version: str
    generated_at: str
    data_mode: Literal["daily_review_v2_first"]
    source: dict[str, Any]
    market_summary: dict[str, Any]
    theme_reviews: list[dict[str, Any]]
    theme_capital_reviews: list[dict[str, Any]]
    strong_stock_reviews: list[dict[str, Any]]
    watchlist_reviews: list[dict[str, Any]]
    stock_capital_reviews: list[dict[str, Any]]
    abnormal_reviews: list[dict[str, Any]]
    money_flow_reviews: list[dict[str, Any]]
    dragon_tiger_reviews: list[dict[str, Any]]
    trading_principle: dict[str, Any]
    diagnostics: DailyReviewDiagnostics
