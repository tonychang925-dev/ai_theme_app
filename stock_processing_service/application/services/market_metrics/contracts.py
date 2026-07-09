"""M2.5 — Market Metrics Contracts.

MarketMetricsSnapshot is the SINGLE canonical fact layer.
All engines (Emotion, Diagnosis, Charts, Workspace) consume from here.
No module queries DB or parses JSON independently.

Key rules:
  - All amounts: internal unit = 亿元 (100M CNY)
  - Every field: value + unit + source + is_calibrated + confidence
  - PDF calibration applied HERE, not in individual consumers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ── Metric source tracking ──

@dataclass(frozen=True, slots=True)
class MetricSource:
    """Where did this metric come from?"""
    source_type: str          # metrics_table / recap_snapshot / db_query / pdf_calibrated / estimate
    source_detail: str = ""   # table name, field name, etc.
    confidence: float = 1.0   # 0-1
    is_calibrated: bool = False


# ── Typed metric with source ──

@dataclass(frozen=True, slots=True)
class TypedMetric:
    value: float
    unit: str
    source: MetricSource
    raw_value: float | None = None  # original value before normalization


# ── Sub-metrics ──

@dataclass(frozen=True, slots=True)
class MarketBreadthMetrics:
    up_count: int; down_count: int
    limit_up_count: int; limit_down_count: int
    up_ratio: float                 # 0-1
    turnover_yi: float              # 亿元
    source: MetricSource


@dataclass(frozen=True, slots=True)
class LimitUpMetrics:
    """Limit-up board statistics with sealed/fried classification.

    Source: ths_hot_reason_snapshot (同花顺涨停原因) with pct_chg for board quality.

    Board thresholds:
      - 主板 (Main):   pct_chg >= 9.5  → sealed
      - 创业板/科创板:  pct_chg >= 19.5 → sealed  (300/301/688/689)
      - 北交所:         pct_chg >= 29.5 → sealed  (8xx/4xx)
      - ST stocks:      pct_chg >= 4.5  → sealed  (name contains "ST")

    Total = sealed + fried (all stocks that touched the limit-up board).
    """
    total_count: int                 # 触及涨停总数 = sealed + fried
    sealed_count: int                # 封板成功数 (pct_chg >= threshold)
    fried_board_count: int           # 炸板数 (hit limit but did not seal)
    chain_board_count: int           # 连板家数 (streak >= 2)
    max_board_height: int            # 最高板（含一字板）
    max_turnover_board_height: int   # 最高换手板
    first_board_count: int           # 首板数
    first_board_success_rate: float  # 首板占比 = first_board_count / total_count
    sealed_board_ratio: float        # 封板率 = sealed_count / total_count
    high_board_count: int            # 高标板数 (>= 3板)
    # ── Board quality ──
    avg_turnover_rate: float | None = None        # 封板成功股平均换手率
    avg_amount_yi: float | None = None            # 封板成功股平均成交额（亿元）
    avg_big_order_net_yi: float | None = None     # 封板成功股平均大单净量（亿元）
    fried_amount_ratio: float | None = None       # 炸板金额 / 总触板金额
    # ── Classification ──
    board_type_counts: dict[str, int] = field(default_factory=dict)
    # ── Provenance ──
    source: MetricSource = field(default_factory=lambda: MetricSource("db_query", "ths_hot_reason_snapshot"))


@dataclass(frozen=True, slots=True)
class RelayEcologyMetrics:
    """Relay ecology — answers: "Did yesterday's traders make money today?"

    v2 adds feedback score and yesterday cross-reference instead of
    pure streak backtracking. Core unit for Emotion Engine cycle detection.
    """
    # ── Promotion rates ──
    promotion_1_to_2: float               # 一进二晋级率
    promotion_2_to_3: float               # 二进三晋级率
    promotion_3_to_4: float               # 三进四晋级率
    chain_board_count: int                # 连板家数
    max_board_height: int                 # 最高板
    max_turnover_board_height: int        # 最高换手板

    # ── Yesterday limit-up feedback (v2) ──
    yesterday_limitup_count: int          # 昨日涨停总数
    today_continue_count: int             # 今日继续涨停数 (昨涨停 ∩ 今涨停)
    continue_ratio: float                 # 接力成功率 = today_continue / yesterday
    yesterday_big_loss_count: int         # 昨涨停今日大面数 (跌 >5%)
    yesterday_avg_return_pct: float | None = None  # 昨涨停股今日平均收益率(%)

    # ── LimitUp Feedback Score (v2) ──
    feedback_score: float = 0.0           # -100 ~ +100 接力反馈分数
    feedback_label: str = ""              # "强正反馈"|"正反馈"|"中性"|"负反馈"|"强负反馈"
    feedback_components: dict[str, float] = field(default_factory=dict)
    # keys: "continue_bonus", "big_loss_penalty", "avg_return_adjust"

    # ── High board health ──
    high_board_count: int = 0             # >= 3板的股票数
    high_board_break_count: int = 0       # 高标断板数 (昨高标 ∧ 今未涨停)

    # ── Provenance ──
    source: MetricSource = field(default_factory=lambda: MetricSource("db_query"))


@dataclass(frozen=True, slots=True)
class LossEffectMetrics:
    """Loss effect — the OTHER side of market microstructure.

    Analysts judge recession NOT by how many stocks went UP,
    but by how many went DOWN HARD. This is the counterweight
    to LimitUpMetrics and RelayMetrics.

    Data sources:
      - limit_down: stock_daily_snapshot (pct_chg <= -threshold)
      - big_loss: reuses relay.yesterday_big_loss_count
      - high_board_break: cross-ref yesterday high-board stocks with today
    """
    # ── Limit down (non-default first) ──
    limit_down_count: int              # 跌停家数
    limit_down_ratio: float            # 跌停/全市场

    # ── Big loss ──
    big_loss_count: int                # 大面数（昨涨停今日跌>5%）

    # ── Optional with defaults ──
    limit_down_amount_yi: float = 0.0
    big_loss_from_yesterday_ratio: float = 0.0
    high_board_break_count: int = 0
    loss_effect_score: float = 0.0
    loss_effect_label: str = ""
    total_damage_count: int = 0
    damage_ratio: float = 0.0
    source: MetricSource = field(default_factory=lambda: MetricSource("db_query"))


@dataclass(frozen=True, slots=True)
class ActiveCapitalMetrics:
    total_turnover_yi: float          # 全市场成交额（亿元）
    active_limitup_amount_yi: float   # 涨停/触板活跃资金成交额（亿元）
    active_ratio: float               # 活跃资金 / 全市场成交额
    source: MetricSource


@dataclass(frozen=True, slots=True)
class EmotionMomentumMetrics:
    # Raw scores (analyst scale, roughly -18 to +10)
    first_board_red_ratio: float
    first_board_big_loss_ratio: float
    chain_board_red_ratio: float
    chain_board_ratio: float         # 连板占比 = chain_board_count / total_count
    chain_board_big_loss_ratio: float
    yesterday_chain_not_limit_red_ratio: float  # 昨连板非涨停红盘比
    momentum_raw: float              # -18 ~ +10 (analyst scale)
    momentum_normalized: float       # -100 ~ +100
    source: MetricSource


@dataclass(frozen=True, slots=True)
class FundFlowMetrics:
    main_net_inflow_yi: float        # 主力净流入（亿元）
    institution_inflow_yi: float     # 机构净流入（亿元）
    hot_money_inflow_yi: float       # 游资净流入（亿元）
    source: MetricSource


# ═══════════════════════════════════════════════════════════════
# Leader Evolution (Phase 2.3)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class LeaderSnapshot:
    """A single leader stock state for one trading day.

    Status values (8-state expectation model):
      NEW                — first detection, no prior to compare
      NORMAL_CONTINUE    — continued as expected (yesterday H → today H+1)
      SUPER_CONTINUE     — exceeded expectation (sealed when expected to break)
      WEAKEN_EXPECTED    — weakened but it was predictable (late-stage fatigue)
      WEAKEN_UNEXPECTED  — weakened when expected to continue (negative surprise)
      BREAK              — did not continue (moderate-strong negative)
      REPLACED           — old leader broke, new leader took over
      CROSS_OVER         — leader jumped themes (interesting signal)
    """
    stock_code: str
    stock_name: str
    board_height: int                # 当前连板高度
    status: str                      # 8-state expectation model
    relative_height: float = 0.0     # board_height / market_max_height (0-1)
    expected_height: int = 0
    surprise_score: float = 0.0
    yesterday_status: str = ""
    strength_score: float = 0.0
    risk_score: float = 0.0
    sealed: bool = True
    theme_hint: str = ""
    reason: str = ""
    death_type: str = ""             # NONE | NORMAL | FRIED | LIMIT_DOWN | HEAVEN_EARTH


@dataclass(frozen=True, slots=True)
class LeaderEvolutionMetrics:
    """Daily leader lifecycle with expectation tracking."""
    trade_date: date
    leaders: tuple[LeaderSnapshot, ...]
    yesterday_leader_count: int = 0
    continue_count: int = 0
    super_continue_count: int = 0
    weaken_expected_count: int = 0
    weaken_unexpected_count: int = 0
    break_count: int = 0
    new_leader_count: int = 0
    replaced_count: int = 0
    leader_health_score: float = 0.0
    leader_health_label: str = ""        # STRONG | NORMAL | WEAK | COLLAPSE
    leader_break_alert: bool = False
    # Expectation summary
    avg_surprise_score: float = 0.0      # -100~+100 average across all leaders
    source: MetricSource = field(default_factory=lambda: MetricSource("db_query"))


# ── Loss Attribution (Phase 2.4) ──

@dataclass(frozen=True, slots=True)
class LossAttributionMetrics:
    """Categorize losses by source — who lost money and why?

    Answers: was today's damage concentrated in high-board stocks,
    yesterday's limit-up stocks, or specific themes?
    """
    trade_date: date

    # ── By position ──
    limit_down_count: int = 0            # total limit-down
    high_board_loss_count: int = 0       # 跌停 ∩ 昨>=2板
    yesterday_limitup_loss_count: int = 0  # 跌停 ∩ 昨涨停
    leader_loss_count: int = 0           # 跌停 ∩ 昨>=3板

    # ── By theme ──
    theme_loss: dict[str, int] = field(default_factory=dict)
    primary_loss_theme: str = ""         # theme with most losses
    primary_loss_count: int = 0

    # ── Risk signal ──
    concentrated_high_board: bool = False  # >30% of losses are high-board
    concentrated_leader: bool = False      # leaders among the loss
    loss_conclusion: str = ""              # one-line narrative

    source: MetricSource = field(default_factory=lambda: MetricSource("db_query"))


@dataclass(frozen=True, slots=True)
class HighPositionDeathMetrics:
    """High Position Death Index — WHO died, not just HOW MANY.

    Core analyst question: Did today's losses hit the CORE positions?

    Formula: leader_break*40% + high_board_loss*30% + yesterday_feedback*20% + big_loss*10%
    """
    death_index: float = 0.0              # 0-100, the composite death index
    death_label: str = ""                 # SAFE | WARNING | DANGER | CRITICAL

    leader_break_count: int = 0           # how many leaders broke
    high_board_loss_count: int = 0        # 高位连板亏损数
    yesterday_feedback_inverted: float = 0.0  # 100 - abs(feedback_score), inverted
    big_loss_count: int = 0               # 大面数

    # Narrative
    death_conclusion: str = ""            # one-line: "高位核心死亡，风险升级至CRITICAL"
    risk_escalation: bool = False         # True if death_index >= 60 (should override risk to CRITICAL)

    source: MetricSource = field(default_factory=lambda: MetricSource("derived"))


# ── Unified snapshot ──

@dataclass(frozen=True, slots=True)
class MarketMetricsSnapshot:
    """Single canonical fact layer for a trading day.

    ALL modules consume this. None query DB independently.
    """
    trade_date: date

    breadth: MarketBreadthMetrics
    limitup: LimitUpMetrics
    relay: RelayEcologyMetrics
    capital: ActiveCapitalMetrics
    emotion_momentum: EmotionMomentumMetrics
    loss_effect: LossEffectMetrics | None = None
    leader_evolution: LeaderEvolutionMetrics | None = None
    loss_attribution: LossAttributionMetrics | None = None
    high_position_death: HighPositionDeathMetrics | None = None
    fund_flow: FundFlowMetrics | None = None

    # Calibration
    calibration_applied: bool = False
    calibration_source: str = ""     # "analyst_pdf" / "analyst_manual"
    calibration_fields: tuple[str, ...] = ()

    # Data quality
    data_quality_score: float = 1.0  # 0-1
    missing_fields: tuple[str, ...] = ()


# ── Unit normalization ──

def normalize_to_yi(value: float, from_unit: str) -> float:
    """Convert to 亿元 (100M CNY)."""
    factors = {
        "yuan": 1e-8,       # 元 → 亿
        "wan": 1e-4,        # 万 → 亿
        "yi": 1.0,          # 亿 → 亿
        "wan_yi": 1e4,      # 万亿 → 亿
    }
    factor = factors.get(from_unit, 1.0)
    return round(value * factor, 2)


def display_amount(value_yi: float) -> str:
    """Display amount in human-readable form."""
    if abs(value_yi) >= 10000:
        return f"{value_yi / 10000:.2f}万亿"
    return f"{value_yi:.0f}亿"


def display_pct(value: float) -> str:
    """Display percentage (0-1 scale input)."""
    if 0 < value <= 1:
        return f"{value * 100:.1f}%"
    return f"{value:.1f}%"
