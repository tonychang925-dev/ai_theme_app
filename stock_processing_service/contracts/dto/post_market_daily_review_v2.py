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


class MarketOverviewNarrative(TypedDict, total=False):
    headline: str
    core_points: list[str]
    market_state_summary: str
    index_summary: str
    sentiment_summary: str
    hotspot_summary: str
    risk_warning: str
    next_day_strategy: str
    source: str
    diagnostics: dict[str, Any]


class MarketHotspotTheme(TypedDict, total=False):
    theme_name: str
    subject_key: str
    limit_up_count: int
    active_mainline: bool
    lifecycle_state: str
    trade_action: str


class MarketHotspotNarrative(TypedDict, total=False):
    headline: str
    core_points: list[str]
    strongest_themes: list[MarketHotspotTheme]
    rotation_themes: list[str]
    risk_themes: list[str]
    market_heat_summary: str
    next_day_focus: str
    source: str
    diagnostics: dict[str, Any]


class MarketHotspotRepresentativeStock(TypedDict, total=False):
    stock_id: str
    stock_name: str
    reason: str | None


class MarketHotspotRow(TypedDict, total=False):
    subject_key: str
    theme_name: str
    limit_up_count: int | None
    first_board_count: int | None
    consecutive_board_count: int | None
    strong_stock_count: int | None
    representative_stocks: list[MarketHotspotRepresentativeStock]
    total_inflow: float | None
    top3_inflow: float | None
    leader_inflow: float | None
    lifecycle_state: str | None
    is_confirmed_mainline: bool
    mainline_name: str | None
    action_advice: str | None
    heat_score: float | None
    rank_order: int | None


class MarketHotspotOverview(TypedDict, total=False):
    summary: str
    hotspot_rows: list[MarketHotspotRow]
    strongest_themes: list[str]
    mainline_related_themes: list[str]
    rotation_themes: list[str]
    risk_themes: list[str]
    source: str
    diagnostics: dict[str, Any]


class LimitUpThemeMatrixBoardGroup(TypedDict, total=False):
    board_count: int
    board_label: str
    stock_count: int
    stocks: list[dict[str, Any]]


class LimitUpThemeMatrixColumn(TypedDict, total=False):
    subject_key: str
    theme_name: str
    limit_up_count: int
    active_mainline: bool
    lifecycle_state: str
    trade_action: str
    mainline_name: str
    focus_stocks: list[dict[str, Any]]
    board_groups: list[LimitUpThemeMatrixBoardGroup]
    catalyst_events: list[dict[str, Any]]


class LimitUpThemeMatrix(TypedDict, total=False):
    summary: str
    columns: list[LimitUpThemeMatrixColumn]
    board_totals: dict[str, int]
    diagnostics: dict[str, Any]

class MainlineNarrative(TypedDict, total=False):
    summary: str
    core_points: list[str]
    divergence_mainlines: list[str]
    fade_mainlines: list[str]
    watch_only_mainlines: list[str]
    action_summary: str
    source: str
    diagnostics: dict[str, Any]

class EvidenceGroup(TypedDict, total=False):
    group_key: Literal["d1", "layer_c", "mainline", "risk", "non_mainline"]
    group_name: str
    summary: str
    item_count: int
    top_stocks: list[str]
    related_mainlines: list[str]


class EvidenceItem(TypedDict, total=False):
    evidence_type: Literal["abnormal", "money_flow", "dragon_tiger", "stock_capital"]
    stock_id: str | None
    stock_code: str | None
    stock_name: str | None
    subject_key: str | None
    theme_name: str | None
    title: str
    description: str
    score: float | None
    amount: float | None
    active_mainline: bool
    mainline_name: str | None
    lifecycle_state: str | None
    in_layer_c: bool
    is_d1_candidate: bool
    is_focus_stock: bool
    trade_action: str | None
    tags: list[str]
    rank_order: int | None
    f10_capital: dict[str, Any]


class EvidenceLayerReview(TypedDict, total=False):
    summary: str
    evidence_groups: list[EvidenceGroup]
    abnormal_evidence: list[EvidenceItem]
    money_flow_evidence: list[EvidenceItem]
    dragon_tiger_evidence: list[EvidenceItem]
    stock_capital_evidence: list[EvidenceItem]
    source: Literal["structured", "fallback"]
    diagnostics: dict[str, Any]

class D1Narrative(TypedDict, total=False):
    summary: str
    candidate_count: int
    focus_count: int
    formal_count: int
    observe_count: int
    confirmation_requirements: list[str]
    invalid_conditions: list[str]
    risk_warning: str
    source: str
    diagnostics: dict[str, Any]


class SeatMoneyActivityEntry(TypedDict, total=False):
    stock_id: str
    stock_name: str
    theme_name: str
    subject_key: str
    buy_amount: float | None
    sell_amount: float | None
    net_amount: float | None
    reason: str | None
    rank_order: int | None
    is_theme_leader: bool
    style_tags: list[str]


class HotMoneySeatRow(TypedDict, total=False):
    hot_money_name: str
    buy_entries: list[SeatMoneyActivityEntry]
    sell_entries: list[SeatMoneyActivityEntry]
    buy_net: float | None
    sell_net: float | None
    net_buy: float | None


class SeatMoneyInstitutionRow(TypedDict, total=False):
    stock_id: str
    stock_name: str
    close_price: float | None
    pct_change: float | None
    buy_seat_count: int | None
    sell_seat_count: int | None
    institution_buy_amount: float | None
    institution_sell_amount: float | None
    net_buy: float | None
    theme_name: str
    reason: str | None
    seat_summary: list[dict[str, Any]]


class PostMarketDailyReviewV2(TypedDict):
    schema_version: Literal["daily_review_v2"]
    trade_date: str
    report_type: Literal["post_market"]
    snapshot_version: str
    generated_at: str
    data_mode: Literal["daily_review_v2_first"]
    source: dict[str, Any]
    market_summary: dict[str, Any]
    market_overview_narrative: MarketOverviewNarrative
    market_hotspot_overview: MarketHotspotOverview
    market_hotspot_narrative: MarketHotspotNarrative
    evidence_layer_review: EvidenceLayerReview
    mainline_narrative: MainlineNarrative
    d1_narrative: D1Narrative
    market_overview_review: dict[str, Any]
    limit_up_theme_matrix: LimitUpThemeMatrix
    daily_recap_essentials: dict[str, Any]
    theme_reviews: list[dict[str, Any]]
    theme_capital_reviews: list[dict[str, Any]]
    strong_stock_reviews: list[dict[str, Any]]
    watchlist_reviews: list[dict[str, Any]]
    stock_capital_reviews: list[dict[str, Any]]
    abnormal_reviews: list[dict[str, Any]]
    money_flow_reviews: list[dict[str, Any]]
    dragon_tiger_reviews: list[dict[str, Any]]
    limit_up_ladder: dict[str, Any]
    limit_up_theme_events: dict[str, Any]
    new_high_summary: dict[str, Any]
    seat_money_summary: dict[str, Any]
    trading_principle: dict[str, Any]
    watchlists: dict[str, Any]
    diagnostics: DailyReviewDiagnostics
