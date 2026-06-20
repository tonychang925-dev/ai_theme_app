from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class StockDailySnapshot:
    trade_date: str
    stock_id: str
    stock_name: Optional[str]
    open_price: Optional[float]
    high_price: Optional[float]
    low_price: Optional[float]
    close_price: Optional[float]
    pre_close: Optional[float]
    pct_chg: Optional[float]
    volume: Optional[float]
    amount: Optional[float]
    source_name: str = "tushare"


@dataclass(frozen=True)
class SubjectStockDailySnapshot:
    trade_date: str
    subject_key: str
    subject_name: Optional[str]
    stock_id: str
    stock_name: Optional[str]
    rank_order: int
    pct_chg: Optional[float]
    close_price: Optional[float]
    is_leader: bool
    source_name: str = "jyhf"


@dataclass(frozen=True)
class StockAbnormalEvent:
    trade_date: str
    stock_id: str
    stock_name: Optional[str]
    subject_key: str
    subject_name: Optional[str]
    abnormal_type: str
    pct_chg: Optional[float]
    rank_order: int
    is_leader: bool
    evidence: str


@dataclass(frozen=True)
class ThemeStockLeaderboardEntry:
    trade_date: str
    subject_key: str
    subject_name: Optional[str]
    stock_id: str
    stock_name: Optional[str]
    rank_order: int
    role: str
    pct_chg: Optional[float]
    close_price: Optional[float]
    limit_up: bool
    score: float


@dataclass(frozen=True)
class ThemeMainlineJudgement:
    trade_date: str
    subject_key: str
    theme_name: str
    event_chain_score: float
    event_chain_continuity_score: float
    market_recognition_score: float
    mainline_stability_score: float
    is_main_theme: bool
    theme_tier: str
    limit_up_count: int
    conclusion: str
    novelty_score: float = 0.0
    timing_score: float = 0.0
    influence_score: float = 0.0
    capital_persistence_score: float = 0.0
    institution_participation_score: float = 0.0
    retail_attention_score: float = 0.0
    evidence_logic: List[str] = field(default_factory=list)
    evidence_market: List[str] = field(default_factory=list)
    source_type: str = "p3.phase2.mainline"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "theme_mainline_judgement.v1"
    rule_version: str = "theme_mainline_judgement.v1"


@dataclass(frozen=True)
class ThemeMainlineStateV2:
    trade_date: str
    subject_key: str
    theme_name: str
    mainline_alive: bool
    mainline_bucket: str
    event_count_3d: float
    event_continuity_score: float
    confidence_score: float
    mainline_strength_score: float
    limit_up_count: int
    final_cycle_state: str
    fade_risk_score: float = 0.0
    conclusion: str = ""
    rule_reasons: List[str] = field(default_factory=list)
    source_type: str = "theme_cycle_judgement_v2"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "theme_cycle_judgement.v2"
    rule_version: str = "theme_cycle_judgement.v2"


@dataclass(frozen=True)
class ThemeCycleJudgement:
    trade_date: str
    subject_key: str
    theme_name: str
    is_main_theme: bool
    is_start: bool
    is_fermentation: bool
    is_divergence: bool
    is_rebound: bool
    is_climax: bool
    is_fade: bool
    primary_cycle_stage: str
    limit_up_count: int
    leader_status: str
    board_effect_status: str
    action_bias: str
    confidence: float
    conclusion: str
    evidence: List[str] = field(default_factory=list)
    source_type: str = "p3.phase2.cycle"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "theme_cycle_judgement.v1"
    rule_version: str = "theme_cycle_judgement.v1"


@dataclass(frozen=True)
class ThemeLeaderCandidate:
    trade_date: str
    subject_key: str
    theme_name: str
    stock_id: str
    stock_name: str
    purity_score: float
    leading_score: float
    capital_score: float
    structure_score: float
    resilience_score: float
    composite_score: float
    is_limit_up: bool
    limit_up_type: str
    turnover_rate: float
    volume_ratio: float
    main_net_inflow: float
    is_new_stock: bool
    candidate_rank: int
    role_label: str
    evidence: List[str] = field(default_factory=list)
    source_type: str = "p3.phase2.leader_candidate"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "theme_leader_candidate.v1"
    rule_version: str = "theme_leader_candidate.v1"


@dataclass(frozen=True)
class ThemeLeaderLlmJudgement:
    trade_date: str
    subject_key: str
    theme_name: str
    candidate_payload: Dict[str, Any] = field(default_factory=dict)
    prompt_text: str = ""
    leader_stock_id: str = ""
    leader_status: str = ""
    confirmation_basis: str = ""
    runner_up_stock_id: str = ""
    card_position_stock_id: str = ""
    supplement_stock_id: str = ""
    eliminated_stock_id: str = ""
    judgement_json: Dict[str, Any] = field(default_factory=dict)
    reasoning_summary: str = ""
    model_name: str = ""
    prompt_version: str = "theme_leader_llm_judgement.v1"
    source_type: str = "p3.phase3.theme_leader_llm_judgement"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "theme_leader_llm_judgement.v1"
    rule_version: str = "theme_leader_llm_judgement.v1"


@dataclass(frozen=True)
class PreMarketExecutionPlan:
    source_trade_date: str
    trade_date: str
    subject_key: str
    theme_name: str
    theme_status: str
    leader_stock_id: str
    leader_stock_name: str
    leader_status: str
    action_today: str
    action_bias: str
    watch_reason: str
    auction_focus_stock_id: str = ""
    auction_focus_stock_name: str = ""
    auction_signal_level: str = ""
    auction_signal_type: str = ""
    auction_action_today: str = ""
    auction_signal_score: float = 0.0
    auction_hard_reject_reason: str = ""
    invalid_conditions: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreMarketAuctionSnapshot:
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    role_label: str
    window_start_time: str = "09:20:00"
    window_end_time: str = "09:25:00"
    last_minute_start_time: str = "09:24:00"
    last_30s_start_time: str = "09:24:30"
    auction_open_price: float = 0.0
    pre_close: float = 0.0
    auction_open_pct: float = 0.0
    auction_volume: float = 0.0
    auction_amount: float = 0.0
    last_minute_amount: float = 0.0
    last_minute_ratio: float = 0.0
    prev_day_max_intraday_amount: float = 0.0
    carry_ratio: float = 0.0
    price_path_stability_score: float = 0.0
    is_red_zone: bool = False
    has_end_spike: bool = False
    has_end_drop: bool = False
    shape_features: List[str] = field(default_factory=list)
    source_type: str = "p3.phase3.auction_snapshot"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "auction_snapshot.v1"
    rule_version: str = "auction_snapshot.v1"


@dataclass(frozen=True)
class PreMarketAuctionSignal:
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    role_label: str
    auction_signal_score: float
    auction_signal_level: str
    signal_type: str
    leader_status: str
    action_today: str
    hard_reject_reason: str = ""
    evidence: List[str] = field(default_factory=list)
    source_type: str = "p3.phase3.auction_signal"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "auction_signal.v1"
    rule_version: str = "auction_signal.v1"


@dataclass(frozen=True)
class PreMarketAuctionSignalValidation:
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    role_label: str
    auction_signal_level: str
    auction_signal_score: float
    signal_type: str
    action_today: str
    close_pct: float = 0.0
    close_price: float = 0.0
    hit_limit_up: bool = False
    close_rank_order: int = 0
    close_is_leader: bool = False
    validation_result: str = ""
    signal_validated: bool = False
    validation_note: str = ""
    source_type: str = "p3.phase3.auction_signal_validation"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "auction_signal_validation.v1.daily_only"
    rule_version: str = "auction_signal_validation.v1.daily_only"


@dataclass(frozen=True)
class AuctionWatchUniverse:
    source_trade_date: str
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    theme_tier: str
    mainline_alive: bool
    primary_cycle_stage: str
    action_bias: str
    role_label: str
    candidate_rank: int
    candidate_priority: str
    is_reversal_watch: bool = False
    source_type: str = "p3.phase3.auction_watch_universe"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "auction_watch_universe.v1"
    rule_version: str = "auction_watch_universe.v1"


@dataclass(frozen=True)
class DragonTigerObject:
    trade_date: str
    stock_id: str
    stock_name: str
    reason: str
    close_price: float
    pct_change: float
    turnover_rate: float
    total_amount: float
    billboard_buy_amount: float
    billboard_sell_amount: float
    billboard_amount: float
    net_amount: float
    net_rate: float
    amount_rate: float
    float_market_value: float
    institution_buy_amount: float
    institution_sell_amount: float
    institution_net_buy: float
    institution_seat_count: int
    seat_summary: List[Dict[str, Any]] = field(default_factory=list)
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "tushare.top_list+top_inst.v1"
    rule_version: str = "dragon_tiger_object.v1"


@dataclass(frozen=True)
class HotMoneySeatMaster:
    seat_name: str
    seat_alias: str
    hot_money_name: str
    style_tags: List[str] = field(default_factory=list)
    confidence: float = 0.0
    is_active: bool = True
    source_version: str = "hot_money_seat_master.v1"
    rule_version: str = "hot_money_seat_master.v1"


@dataclass(frozen=True)
class HotMoneyTradingActivity:
    trade_date: str
    hot_money_name: str
    seat_name: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    side: str
    buy_amount: float
    sell_amount: float
    net_amount: float
    reason: str
    rank_order: int = 0
    is_theme_leader: bool = False
    style_tags: List[str] = field(default_factory=list)
    source_version: str = "hot_money_trading_activity.v1"
    rule_version: str = "hot_money_trading_activity.v1"


@dataclass(frozen=True)
class MoneyFlowEnhanced:
    trade_date: str
    subject_key: str
    theme_name: str
    stock_id: str
    stock_name: str
    role_label: str
    role_enhanced: str
    candidate_rank: int
    composite_score: float
    activity_score: float
    capital_flow_score: float
    money_flow_score: float
    money_flow_tier: str
    turnover_rate: float
    volume_ratio: float
    main_net_inflow: float
    dragon_tiger_net_amount: float
    institution_seat_count: int
    explanation: List[str] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)
    source_type: str = "p3.phase2.money_flow"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "money_flow_enhanced.v1"
    rule_version: str = "money_flow_enhanced.v1"


@dataclass(frozen=True)
class MarketEnvironmentMetrics:
    trade_date: str
    up_count: int
    down_count: int
    flat_count: int
    advance_decline_ratio: float
    limit_up_count: int
    limit_down_count: int
    limit_up_down_ratio: float
    yesterday_limit_up_open_strength: float
    yesterday_limit_up_open_red_ratio: float
    yesterday_limit_up_premium_ratio: float
    yesterday_limit_up_fade_ratio: float
    yesterday_limit_up_fail_ratio: float
    morning_high_then_fall_count: int
    morning_high_then_fall_ratio: float
    intraday_fade_count: int
    intraday_fade_ratio: float
    high_mark_strong_count: int
    high_mark_weak_count: int
    market_volume_change_pct: float
    market_avg_open_pct: float
    market_avg_close_pct: float
    market_total_amount: float = 0.0
    shanghai_index_pct_chg: float = 0.0
    open_close_pullback_count: int = 0
    open_close_pullback_ratio: float = 0.0
    source_type: str = "p3.phase3.market_environment_metrics"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "market_environment_metrics.v1.daily_proxy"
    rule_version: str = "market_environment_metrics.v1.daily_proxy"


@dataclass(frozen=True)
class MarketEnvironmentJudgement:
    trade_date: str
    market_health_score: float
    market_bias: str
    breadth_status: str
    short_term_sentiment_status: str
    relay_sentiment_status: str
    intraday_fade_status: str
    action_bias: str
    conclusion: str
    evidence: List[str] = field(default_factory=list)
    source_type: str = "p3.phase3.market_environment_judgement"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "market_environment_judgement.v1.daily_proxy"
    rule_version: str = "market_environment_judgement.v1.daily_proxy"


@dataclass(frozen=True)
class ThemeEnvironmentJudgement:
    trade_date: str
    subject_key: str
    theme_name: str
    board_health_status: str
    board_effect_status: str
    leader_support_status: str
    follow_strength_status: str
    action_bias: str
    conclusion: str
    evidence: List[str] = field(default_factory=list)
    source_type: str = "p3.phase3.theme_environment_judgement"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "theme_environment_judgement.v1"
    rule_version: str = "theme_environment_judgement.v1"


@dataclass(frozen=True)
class StockPositionJudgement:
    trade_date: str
    stock_id: str
    stock_name: str
    position_label: str
    distance_to_20d_high: float
    distance_to_60d_high: float
    distance_to_120d_high: float
    distance_to_all_time_high: float
    ma_alignment_status: str
    trend_strength_score: float
    conclusion: str
    evidence: List[str] = field(default_factory=list)
    source_type: str = "p3.phase3.stock_position"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "stock_position_judgement.v1"
    rule_version: str = "stock_position_judgement.v1"


@dataclass(frozen=True)
class StockPatternJudgement:
    trade_date: str
    stock_id: str
    stock_name: str
    pattern_labels: List[str]
    volume_pattern_status: str
    breakout_status: str
    pullback_status: str
    risk_pattern_status: str
    conclusion: str
    evidence: List[str] = field(default_factory=list)
    source_type: str = "p3.phase3.stock_pattern"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "stock_pattern_judgement.v1"
    rule_version: str = "stock_pattern_judgement.v1"


@dataclass
class StockAbnormalSignal:
    trade_date: str
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    turnover_rate: float
    turnover_rank_in_theme: int
    main_net_inflow: float
    main_net_inflow_rank_in_theme: int
    turnover_abnormal_score: float
    capital_focus_score: float
    is_high_turnover: bool
    is_extreme_turnover: bool
    volume_ratio_to_ma50: float
    volume_abnormal_score: float
    is_volume_breakout: bool
    is_double_volume: bool
    is_high_volume_bar: bool
    tail_amount: float
    tail_amount_ratio: float
    tail_unmatched_buy_order: float
    tail_abnormal_score: float
    has_tail_rush_buy: bool
    has_tail_large_unmatched_bid: bool
    hot_money_buy_names: List[str] = field(default_factory=list)
    institution_net_buy: float = 0.0
    institution_seat_count: int = 0
    has_hot_money_buy: bool = False
    has_institution_buy: bool = False
    abnormal_labels: List[str] = field(default_factory=list)
    abnormal_composite_score: float = 0.0
    conclusion: str = ""
    evidence: List[str] = field(default_factory=list)
    source_type: str = "p3.phase3.stock_abnormal_signal"
    source_trace_id: str = ""
    source_trace: Dict[str, Any] = field(default_factory=dict)
    source_version: str = "stock_abnormal_signal.v1.daily_proxy"
    rule_version: str = "stock_abnormal_signal.v1.daily_proxy"


@dataclass
class IntelEvent:
    occurred_at: str
    subject_key: str
    theme_name: str
    summary: str
    source_type: str = "jyhf_history"


@dataclass
class ThemeStockRollup:
    subject_key: str
    theme_name: str
    leader_stock_name: Optional[str]
    leader_stock_id: Optional[str]
    leader_pct_chg: Optional[float]
    limit_up_count: int
    top_stock_names: List[str] = field(default_factory=list)


@dataclass
class MarketReport:
    report_type: str
    trade_date: str
    title: str
    summary: str
    highlights: List[str]
    sections: List[tuple[str, List[str]]]

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", "", self.summary, ""]
        if self.highlights:
            lines.append("## 核心要点")
            for item in self.highlights:
                lines.append(f"- {item}")
            lines.append("")
        for heading, items in self.sections:
            lines.append(f"## {heading}")
            if items:
                for item in items:
                    lines.append(f"- {item}")
            else:
                lines.append("- 暂无数据")
            lines.append("")
        return "\n".join(lines).strip() + "\n"


@dataclass
class StrongStockRecord:
    """强势股记录，用于维护一周内的龙头/强势股清单"""
    stock_id: str
    stock_name: str
    theme_name: str  # 所属主题
    dragon_head_level: str  # 龙头级别: absolute/relative/sector/none
    strong_reason: str  # 强势原因: leader_dragon_head/strong_signal/high_score等
    first_marked_date: str  # 首次标记日期
    last_marked_date: str  # 最近标记日期
    marked_days_count: int = 1  # 标记天数
    last_day_data: Optional[Dict[str, Any]] = None  # 最近一日数据
    weak_to_strong_candidate: bool = False  # 是否弱转强候选
    technical_support: Optional[Dict[str, Any]] = None  # 技术支撑位信息
    next_day_focus: bool = False  # 是否是第二天重点观察对象
    source_type: str = "p3.phase3.strong_stock_tracker"
    source_trace: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class StrongStockList:
    """强势股清单，按日期组织的强势股集合"""
    trade_date: str  # 清单日期
    strong_stocks: List[StrongStockRecord] = field(default_factory=list)  # 当日强势股
    previous_days_stocks: Dict[str, List[StrongStockRecord]] = field(default_factory=dict)  # 前几日的强势股
    candidate_count: int = 0  # 候选股数量
    weak_to_strong_candidates: List[StrongStockRecord] = field(default_factory=list)  # 弱转强候选股
    next_day_focus_stocks: List[StrongStockRecord] = field(default_factory=list)  # 次日重点观察对象
    source_type: str = "p3.phase3.strong_stock_list"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
