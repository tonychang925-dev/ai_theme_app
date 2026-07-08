"""M2.5 — Metric Registry (Phase 1 + Enhancements).

Every canonical market metric MUST be registered here.
No module may compute a metric independently — it must be consumed
from MarketMetricsService.

Capabilities:
  1. Documentation: which metric comes from where
  2. Quality: freshness, completeness, confidence per metric
  3. Dependency Graph: which derived metrics depend on which base metrics
  4. Governance: CI can assert no unregistered SQL queries
  5. Lineage: auto-generated /api/v1/metrics/lineage

Architecture principle:
  Raw Data → MarketMetricsService (SINGLE owner) → Consumers
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Metric Quality ──

@dataclass(frozen=True, slots=True)
class MetricQuality:
    """Data quality profile for a metric.

    Used by DiagnosisEngine to weight evidence by trustworthiness.
    """
    freshness: str           # "T+0" | "T+1" | "historical" | "varies"
    completeness: float      # 0-1 estimated coverage of the market phenomenon
    confidence: float        # 0-1 source reliability
    notes: str = ""          # e.g. "LLM-generated, subject to revision"


# ── Metric Definition ──

@dataclass(frozen=True, slots=True)
class MetricDefinition:
    """A single canonical market metric.

    Owner is ALWAYS MarketMetricsService unless explicitly justified
    in an ADR.
    """
    name: str                          # canonical key, e.g. "limit_up_total_count"
    display_name: str                  # human-readable, e.g. "涨停数"
    description: str                   # what it measures
    owner: str                         # owning module
    source_tables: tuple[str, ...]     # raw data tables
    source_fields: tuple[str, ...]     # specific fields used
    calculator: str                    # method name in MarketMetricsService
    consumers: tuple[str, ...]         # modules that consume this metric
    unit: str                          # e.g. "count", "ratio_0_1", "yi", "pct", "score"
    version: str                       # semantic version
    quality: MetricQuality = field(default_factory=lambda: MetricQuality(
        freshness="T+0", completeness=0.90, confidence=0.90))
    depends_on: tuple[str, ...] = ()   # metric names this one is derived from
    tags: tuple[str, ...] = ()         # e.g. ("emotion", "relay")


# ── Registry ──

REGISTRY: dict[str, MetricDefinition] = {}


def register(m: MetricDefinition) -> MetricDefinition:
    REGISTRY[m.name] = m
    return m


# ═══════════════════════════════════════════════════════════════════════
# Metric Definitions
# ═══════════════════════════════════════════════════════════════════════

# ── Limit Up (base: ths_hot_reason_snapshot, high confidence) ──

_Q_LIMITUP_BASE = MetricQuality(
    freshness="T+0", completeness=0.95, confidence=0.95,
    notes="同花顺交易所行情，T+0盘后采集",
)

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
    quality=_Q_LIMITUP_BASE,
    tags=("limitup", "emotion", "base"),
))

register(MetricDefinition(
    name="limit_up_sealed_count",
    display_name="封板成功数",
    description="触及涨停且收盘 pct_chg >= limit_threshold 的股票数",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard"),
    unit="count",
    version="1.1",
    quality=_Q_LIMITUP_BASE,
    depends_on=("limit_up_total_count",),
    tags=("limitup", "emotion", "quality", "base"),
))

register(MetricDefinition(
    name="limit_up_fried_count",
    display_name="炸板数",
    description="触及涨停但收盘未封住 (pct_chg < limit_threshold) 的股票数",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard"),
    unit="count",
    version="1.1",
    quality=_Q_LIMITUP_BASE,
    depends_on=("limit_up_total_count", "limit_up_sealed_count"),
    tags=("limitup", "emotion", "quality", "risk", "base"),
))

register(MetricDefinition(
    name="limit_up_sealed_ratio",
    display_name="封板率",
    description="sealed_count / total_count — 封板质量核心指标",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard", "PlaybookEngine"),
    unit="ratio_0_1",
    version="1.1",
    quality=MetricQuality(freshness="T+0", completeness=0.95, confidence=0.95,
                          notes="从 base metrics 推导，置信度继承"),
    depends_on=("limit_up_total_count", "limit_up_sealed_count"),
    tags=("limitup", "emotion", "quality"),
))

# ── Chain Board / Relay (derived from limitup base) ──

_Q_RELAY = MetricQuality(
    freshness="T+0", completeness=0.90, confidence=0.85,
    notes="streak回溯计算；升级到昨涨停池JOIN后confidence→0.95",
)

register(MetricDefinition(
    name="chain_board_count",
    display_name="连板家数",
    description="涨停股中连续 >= 2 日出现在涨停池中的股票数 (streak >= 2)",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_limitup (streak回溯)",
    consumers=("DiagnosisEngine", "RelayEcologyChart", "LeaderEvolutionEngine"),
    unit="count",
    version="1.1",
    quality=_Q_RELAY,
    depends_on=("limit_up_total_count",),
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
    quality=_Q_RELAY,
    depends_on=("chain_board_count",),
    tags=("relay", "emotion"),
))

register(MetricDefinition(
    name="promotion_1_to_2",
    display_name="一进二晋级率",
    description="streak >= 2 / streak >= 1",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_relay (streak_dist)",
    consumers=("RelayEcologyChart", "PlaybookEngine"),
    unit="ratio_0_1",
    version="1.1",
    quality=_Q_RELAY,
    depends_on=("chain_board_count", "limit_up_total_count"),
    tags=("relay",),
))

register(MetricDefinition(
    name="promotion_2_to_3",
    display_name="二进三晋级率",
    description="streak >= 3 / streak >= 2",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_relay (streak_dist)",
    consumers=("RelayEcologyChart", "PlaybookEngine"),
    unit="ratio_0_1",
    version="1.1",
    quality=_Q_RELAY,
    depends_on=("chain_board_count", "promotion_1_to_2"),
    tags=("relay",),
))

register(MetricDefinition(
    name="promotion_3_to_4",
    display_name="三进四晋级率",
    description="streak >= 4 / streak >= 3",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_relay (streak_dist)",
    consumers=("RelayEcologyChart",),
    unit="ratio_0_1",
    version="1.1",
    quality=_Q_RELAY,
    depends_on=("chain_board_count", "promotion_2_to_3"),
    tags=("relay",),
))

# ── Relay v2: Yesterday feedback ──

_Q_FEEDBACK = MetricQuality(
    freshness="T+0", completeness=0.80, confidence=0.75,
    notes="昨涨停∩今数据交叉验证; 升级到昨涨停池后confidence→0.90",
)

register(MetricDefinition(
    name="yesterday_limitup_feedback",
    display_name="昨日涨停反馈",
    description="昨天打板的人今天赚钱了吗？接力成功率 + 大面率 + 反馈分数",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot", "stock_daily_snapshot"),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_relay (yesterday cross-ref)",
    consumers=("DiagnosisEngine", "EmotionDashboard", "PlaybookEngine"),
    unit="composite",
    version="2.0",
    quality=_Q_FEEDBACK,
    depends_on=("chain_board_count", "limit_up_total_count"),
    tags=("relay", "emotion", "feedback"),
))

register(MetricDefinition(
    name="limitup_feedback_score",
    display_name="接力反馈分数",
    description="-100 ~ +100：继续涨停得分 - 大面扣分 + 平均收益调整",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot", "stock_daily_snapshot"),
    source_fields=("stock_code", "pct_chg"),
    calculator="_build_relay (feedback_score)",
    consumers=("DiagnosisEngine", "EmotionDashboard", "PlaybookEngine"),
    unit="score",
    version="2.0",
    quality=_Q_FEEDBACK,
    depends_on=("yesterday_limitup_feedback", "chain_board_count"),
    tags=("relay", "emotion", "feedback", "derived"),
))

register(MetricDefinition(
    name="high_board_count",
    display_name="高标板数",
    description="streak >= 3 的股票数 — 高标生态核心指标",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("stock_code",),
    calculator="_build_limitup",
    consumers=("RelayEcologyChart", "PlaybookEngine"),
    unit="count",
    version="1.1",
    quality=_Q_RELAY,
    depends_on=("chain_board_count", "max_board_height"),
    tags=("relay", "emotion"),
))

# ── Market Breadth (source: LLM recap, medium confidence) ──

_Q_BREADTH = MetricQuality(
    freshness="T+0", completeness=0.90, confidence=0.75,
    notes="LLM recap生成；升级到交易所原始数据后confidence→0.95",
)

register(MetricDefinition(
    name="market_turnover_yi",
    display_name="全市场成交额",
    description="全市场总成交额（亿元），单位已归一化",
    owner="MarketMetricsService",
    source_tables=("post_market_recap_snapshot",),
    source_fields=("market_overview_review.total_amount",),
    calculator="_build_breadth",
    consumers=("DiagnosisEngine", "ChartEngine", "EmotionDashboard", "AnalystWorkspace"),
    unit="yi",
    version="1.1",
    quality=_Q_BREADTH,
    tags=("breadth", "capital", "base"),
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
    quality=_Q_BREADTH,
    tags=("breadth", "base"),
))

# ── Active Capital (source: stock_daily_snapshot, medium confidence) ──

_Q_CAPITAL = MetricQuality(
    freshness="T+0", completeness=0.85, confidence=0.80,
    notes="stock_daily_snapshot pct_chg>=5% 过滤；阈值为估算值",
)

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
    quality=_Q_CAPITAL,
    depends_on=("market_turnover_yi",),
    tags=("capital", "emotion", "base"),
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
    quality=_Q_CAPITAL,
    depends_on=("active_capital_amount_yi", "market_turnover_yi"),
    tags=("capital",),
))

# ── Emotion Momentum (derived composite, lower confidence) ──

_Q_EMOTION = MetricQuality(
    freshness="T+0", completeness=0.80, confidence=0.70,
    notes="从 breadth + limitup 多因子推导；公式源自分析师经验权重",
)

register(MetricDefinition(
    name="emotion_momentum_raw",
    display_name="情绪动能（原始值）",
    description="-18 ~ +10 分析师尺度情绪动能，六因子加权",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot", "post_market_recap_snapshot"),
    source_fields=("pct_chg", "up_count", "down_count"),
    calculator="_build_momentum",
    consumers=("DiagnosisEngine", "EmotionDashboard", "PlaybookEngine"),
    unit="score",
    version="1.1",
    quality=_Q_EMOTION,
    depends_on=("limit_up_total_count", "limit_up_sealed_ratio",
                "market_up_ratio", "chain_board_count"),
    tags=("emotion", "derived"),
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
    quality=_Q_EMOTION,
    depends_on=("emotion_momentum_raw",),
    tags=("emotion", "derived"),
))

# ── Board Quality (limitup detail, high confidence) ──

register(MetricDefinition(
    name="avg_sealed_turnover_rate",
    display_name="封板成功股平均换手率",
    description="所有封板成功股票的平均换手率（筹码活跃度）",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("turnover_rate", "pct_chg"),
    calculator="_build_limitup",
    consumers=("ChartEngine", "LeaderEvolutionEngine"),
    unit="pct",
    version="1.1",
    quality=_Q_LIMITUP_BASE,
    depends_on=("limit_up_sealed_count",),
    tags=("limitup", "quality", "chip"),
))

register(MetricDefinition(
    name="fried_amount_ratio",
    display_name="炸板金额占比",
    description="炸板股票成交额 / 所有触板股票成交额 — 分歧强度指标",
    owner="MarketMetricsService",
    source_tables=("ths_hot_reason_snapshot",),
    source_fields=("amount", "pct_chg"),
    calculator="_build_limitup",
    consumers=("DiagnosisEngine", "ChartEngine"),
    unit="ratio_0_1",
    version="1.1",
    quality=_Q_LIMITUP_BASE,
    depends_on=("limit_up_fried_count", "limit_up_total_count"),
    tags=("limitup", "quality", "risk"),
))


# ═══════════════════════════════════════════════════════════════════════
# Dependency Graph
# ═══════════════════════════════════════════════════════════════════════

def get_dependency_graph() -> dict[str, Any]:
    """Build full DAG: which metrics depend on which.

    Returns:
        {
          "base_metrics": [metrics with no deps — raw data inputs],
          "derived_metrics": [metrics that depend on others],
          "dag": {metric: [dependencies, ...]},
          "reverse_dag": {metric: [dependents, ...]},  # who depends on me
          "evidence_chains": {derived_metric: [base → mid → derived], ...}
        }
    """
    base: list[str] = []
    derived: list[str] = []
    dag: dict[str, list[str]] = {}
    reverse_dag: dict[str, list[str]] = {}

    for name, m in REGISTRY.items():
        if m.depends_on:
            derived.append(name)
            dag[name] = list(m.depends_on)
            for dep in m.depends_on:
                reverse_dag.setdefault(dep, []).append(name)
        else:
            base.append(name)

    # Build evidence chains: for each derived metric, walk deps to leaves
    evidence_chains: dict[str, list[list[str]]] = {}

    def _walk_chain(metric: str, visited: set | None = None) -> list[list[str]]:
        if visited is None:
            visited = set()
        if metric in visited:
            return [[metric]]  # cycle guard
        visited.add(metric)
        deps = dag.get(metric, [])
        if not deps:
            return [[metric]]
        chains: list[list[str]] = []
        for dep in deps:
            for sub in _walk_chain(dep, visited.copy()):
                chains.append([metric] + sub)
        return chains

    for name in derived:
        evidence_chains[name] = _walk_chain(name)

    return {
        "base_metrics": sorted(base),
        "derived_metrics": sorted(derived),
        "dag": {k: sorted(v) for k, v in sorted(dag.items())},
        "reverse_dag": {k: sorted(v) for k, v in sorted(reverse_dag.items())},
        "evidence_chains": {
            k: [list(reversed(c)) for c in v]  # leaf (base) → root (derived)
            for k, v in sorted(evidence_chains.items())
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# Lineage API helpers
# ═══════════════════════════════════════════════════════════════════════

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


def get_quality_summary() -> dict[str, Any]:
    """Summarize quality across all metrics."""
    confidences = [m.quality.confidence for m in REGISTRY.values()]
    return {
        "avg_confidence": round(sum(confidences) / max(len(confidences), 1), 3),
        "min_confidence": min(confidences),
        "max_confidence": max(confidences),
        "high_confidence_count": sum(1 for c in confidences if c >= 0.90),
        "medium_confidence_count": sum(1 for c in confidences if 0.70 <= c < 0.90),
        "low_confidence_count": sum(1 for c in confidences if c < 0.70),
    }


def to_lineage_dict() -> dict[str, Any]:
    """Generate full data lineage report with quality and dependencies."""
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
            "quality": {
                "freshness": m.quality.freshness,
                "completeness": m.quality.completeness,
                "confidence": m.quality.confidence,
                "notes": m.quality.notes,
            },
            "depends_on": list(m.depends_on),
            "tags": list(m.tags),
        }
    return {
        "registry_version": "1.1",
        "metric_count": len(REGISTRY),
        "metrics": metrics,
        "quality_summary": get_quality_summary(),
        "dependency_graph": get_dependency_graph(),
        "consumer_index": {k: sorted(v) for k, v in get_consumer_index().items()},
        "source_index": {k: sorted(v) for k, v in get_source_index().items()},
    }
