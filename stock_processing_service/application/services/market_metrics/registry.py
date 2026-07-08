"""M2.5 — Metric Registry (Phase 1).

Every canonical market metric MUST be registered here.
No module may compute a metric independently — it must be consumed
from MarketMetricsService.

This registry serves three purposes:
  1. Documentation: which metric comes from where
  2. Governance: CI can assert no unregistered SQL queries
  3. Lineage: auto-generated /api/v1/metrics/lineage

Architecture principle:
  Raw Data → MarketMetricsService (SINGLE owner) → Consumers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """A single canonical market metric.

    Owner is ALWAYS MarketMetricsService unless explicitly justified
    in an ADR.
    """
    name: str                          # canonical key, e.g. "limit_up_count"
    display_name: str                  # human-readable, e.g. "涨停数"
    description: str                   # what it measures
    owner: str                         # owning module — almost always "MarketMetricsService"
    source_tables: tuple[str, ...]     # raw data tables
    source_fields: tuple[str, ...]     # specific fields used
    calculator: str                    # method name in MarketMetricsService
    consumers: tuple[str, ...]         # modules that consume this metric
    unit: str                          # e.g. "count", "ratio_0_1", "yi"
    version: str                       # semantic version
    tags: tuple[str, ...] = ()         # e.g. ("emotion", "relay")


# ── Registry ──

REGISTRY: dict[str, MetricDefinition] = {}


def register(m: MetricDefinition) -> MetricDefinition:
    REGISTRY[m.name] = m
    return m


# ── Metric Definitions ──

# --- Limit Up ---

register(MetricDefinition(
    name="limit_up_total_count",
    display_name="涨停数（触及）",
    description="所有触及涨停板的股票数量 = sealed + fried",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard", "AnalystWorkspace"),
    unit="count",
    version="1.1",
    tags=("limitup", "emotion"),
))

register(MetricDefinition(
    name="limit_up_sealed_count",
    display_name="封板成功数",
    description="触及涨停且收盘价 >= 涨停阈值(stock_count with pct_chg >= limit_threshold)",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard"),
    unit="count",
    version="1.1",
    tags=("limitup", "emotion", "quality"),
))

register(MetricDefinition(
    name="limit_up_fried_count",
    display_name="炸板数",
    description="触及涨停但收盘未封住的股票数量(pct_chg < limit_threshold)",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard"),
    unit="count",
    version="1.1",
    tags=("limitup", "emotion", "quality", "risk"),
))

register(MetricDefinition(
    name="limit_up_sealed_ratio",
    display_name="封板率",
    description="封板成功数 / 触及涨停总数",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard", "PlaybookEngine"),
    unit="ratio_0_1",
    version="1.1",
    tags=("limitup", "emotion", "quality"),
))

# --- Chain Board / Relay ---

register(MetricDefinition(
    name="chain_board_count",
    display_name="连板家数",
    description="涨停股中连续 >= 2 日出现在涨停池中的股票数(streak >= 2)",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_limitup (streak回溯)",
    consumers=("DiagnosisEngine", "RelayEcologyChart", "LeaderEvolutionEngine"),
    unit="count",
    version="1.1",
    tags=("relay", "emotion"),
))

register(MetricDefinition(
    name="max_board_height",
    display_name="最高板",
    description="所有涨停股中的最大连续涨停天数",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_limitup (max streak)",
    consumers=("DiagnosisEngine", "RelayEcologyChart", "PlaybookEngine"),
    unit="count",
    version="1.1",
    tags=("relay", "emotion"),
))

register(MetricDefinition(
    name="promotion_1_to_2",
    display_name="一进二晋级率",
    description="连板数 >= 2 / 连板数 >= 1",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_relay (streak_dist)",
    consumers=("RelayEcologyChart", "PlaybookEngine"),
    unit="ratio_0_1",
    version="1.1",
    tags=("relay",),
))

register(MetricDefinition(
    name="promotion_2_to_3",
    display_name="二进三晋级率",
    description="连板数 >= 3 / 连板数 >= 2",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_relay (streak_dist)",
    consumers=("RelayEcologyChart", "PlaybookEngine"),
    unit="ratio_0_1",
    version="1.1",
    tags=("relay",),
))

register(MetricDefinition(
    name="promotion_3_to_4",
    display_name="三进四晋级率",
    description="连板数 >= 4 / 连板数 >= 3",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_relay (streak_dist)",
    consumers=("RelayEcologyChart",),
    unit="ratio_0_1",
    version="1.1",
    tags=("relay",),
))

register(MetricDefinition(
    name="high_board_count",
    display_name="高标板数",
    description="连板数 >= 3 的股票数",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_limitup",
    consumers=("RelayEcologyChart", "PlaybookEngine"),
    unit="count",
    version="1.1",
    tags=("relay", "emotion"),
))

# --- Market Breadth ---

register(MetricDefinition(
    name="market_turnover_yi",
    display_name="全市场成交额",
    description="全市场总成交额（亿元）",
    owner="MarketMetricsService",
    source_tables=("post_market_recap_snapshot",),
    source_fields=("market_overview_review.total_amount",),
    calculator="_build_breadth",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard", "AnalystWorkspace"),
    unit="yi",
    version="1.1",
    tags=("breadth", "capital"),
))

register(MetricDefinition(
    name="market_up_ratio",
    display_name="上涨比例",
    description="上涨家数 / (上涨+下跌)",
    owner="MarketMetricsService",
    source_tables=("post_market_recap_snapshot",),
    source_fields=("market_overview_review.up_count", "market_overview_review.down_count"),
    calculator="_build_breadth",
    consumers=("DiagnosisEngine", "ChartEngine"),
    unit="ratio_0_1",
    version="1.1",
    tags=("breadth",),
))

# --- Active Capital ---

register(MetricDefinition(
    name="active_capital_amount_yi",
    display_name="活跃资金",
    description="涨幅 >= 5% 股票的成交额合计（亿元）",
    owner="MarketMetricsService",
    source_tables=("stock_daily_snapshot",),
    source_fields=("amount", "pct_chg"),
    calculator="_build_capital",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard"),
    unit="yi",
    version="1.1",
    tags=("capital", "emotion"),
))

register(MetricDefinition(
    name="active_capital_ratio",
    display_name="活跃资金占比",
    description="活跃资金 / 全市场成交额",
    owner="MarketMetricsService",
    source_tables=("stock_daily_snapshot", "post_market_recap_snapshot"),
    source_fields=("amount", "pct_chg", "total_amount"),
    calculator="_build_capital",
    consumers=("DiagnosisEngine", "ChartEngine"),
    unit="ratio_0_1",
    version="1.1",
    tags=("capital",),
))

# --- Emotion Momentum ---

register(MetricDefinition(
    name="emotion_momentum_raw",
    display_name="情绪动能（原始值）",
    description="-18 ~ +10 分析师尺度情绪动能",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot", "post_market_recap_snapshot"),
    source_fields=("pct_chg", "up_count", "down_count"),
    calculator="_build_momentum",
    consumers=("DiagnosisEngine", "EmotionDashboard", "PlaybookEngine"),
    unit="score",
    version="1.1",
    tags=("emotion",),
))

register(MetricDefinition(
    name="emotion_momentum_normalized",
    display_name="情绪动能（归一化）",
    description="-100 ~ +100 归一化情绪动能",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot", "post_market_recap_snapshot"),
    source_fields=("pct_chg", "up_count", "down_count"),
    calculator="_build_momentum",
    consumers=("DiagnosisEngine", "EmotionDashboard"),
    unit="score",
    version="1.1",
    tags=("emotion",),
))

# --- Board Quality ---

register(MetricDefinition(
    name="avg_sealed_turnover_rate",
    display_name="封板成功股平均换手率",
    description="所有封板成功股票的平均换手率",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("turnover_rate", "pct_chg"),
    calculator="_build_limitup",
    consumers=("ChartEngine", "LeaderEvolutionEngine"),
    unit="pct",
    version="1.1",
    tags=("limitup", "quality", "chip"),
))

register(MetricDefinition(
    name="fried_amount_ratio",
    display_name="炸板金额占比",
    description="炸板股票成交额 / 所有触板股票成交额",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("amount", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine"),
    unit="ratio_0_1",
    version="1.1",
    tags=("limitup", "quality", "risk"),
))


# ── Lineage API helpers ──

def get_consumer_index() -> dict[str, list[str]]:
    """Build consumer → metrics index for reverse lookup."""
    index: dict[str, list[str]] = {}
    for name, m in REGISTRY.items():
        for consumer in m.consumers:
            index.setdefault(consumer, []).append(name)
    return index


def get_source_index() -> dict[str, list[str]]:
    """Build source_table → metrics index."""
    index: dict[str, list[str]] = {}
    for name, m in REGISTRY.items():
        for table in m.source_tables:
            index.setdefault(table, []).append(name)
    return index


def to_lineage_dict() -> dict[str, Any]:
    """Generate full data lineage report."""
    metrics = {}
    for name, m in sorted(REGISTRY.items()):
        metrics[name] = {
            "display_name": m.display_name,
            "description": m.description,
            "owner": m.owner,
            "source": list(m.source_tables),
            "source_fields": list(m.source_fields),
            "calculator": m.calculator,
            "consumers": list(m.consumers),
            "unit": m.unit,
            "version": m.version,
            "tags": list(m.tags),
        }
    return {
        "registry_version": "1.0",
        "metric_count": len(REGISTRY),
        "metrics": metrics,
        "consumer_index": {k: sorted(v) for k, v in get_consumer_index().items()},
        "source_index": {k: sorted(v) for k, v in get_source_index().items()},
    }
