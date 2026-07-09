"""Phase 4.1b — Analyst Reference Contracts.

Defines the structured format for analyst ground truth data,
enabling AI↔Analyst comparison, calibration, and replay.

Phase 4.1.1 additions:
  - ExtractionStatus (5-level: core_complete/full_complete/partial/needs_review/failed)
  - ExtractedField (field-level evidence with provenance)
  - AnalystReferenceQuality (coverage tracking + missing/low_confidence fields)
  - MISSING sentinel (distinct from None, 0, "")
  - normalize_ratio / normalize_int utilities
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


# ═══ Sentinel for missing values (distinct from None, 0, "") ═══

MISSING: Any = object()


# ═══ Extraction Status ═══

class ExtractionStatus(str, Enum):
    """5-level extraction quality — not the old binary complete/partial."""
    CORE_COMPLETE = "core_complete"    # limit_up_count + max_board_height + market_phase + risk_level + emotion_momentum
    FULL_COMPLETE = "full_complete"    # CORE + relay + strategy + theme_lifecycle + limitup_attribution + leader_state
    PARTIAL = "partial"                # 部分字段缺失，但可用于人工审核
    NEEDS_REVIEW = "needs_review"      # 解析结果不确定（低置信或冲突），需分析师确认
    FAILED = "failed"                  # 无法作为基准数据（如文件损坏、格式不识别）


# ═══ Normalization Utilities ═══

def normalize_ratio(value: str | float | int | None) -> float | None:
    """Unify percentage representations to internal ratio (0.0–1.0).

    '21%'  -> 0.21
    '0.21' -> 0.21
    21     -> 0.21  (value > 1 treated as percentage-point notation)
    0.21   -> 0.21
    None    -> None
    '—'     -> None  (Chinese em-dash = explicitly missing)
    '-'     -> None
    '无'    -> None
    '未提及' -> None
    ''      -> None
    """
    if value is None or value is MISSING:
        return None

    if isinstance(value, str):
        stripped = value.strip()
        if stripped in ("—", "-", "无", "未提及", "N/A", "n/a", "", "null", "Null"):
            return None
        if stripped.endswith("%"):
            try:
                return float(stripped[:-1]) / 100.0
            except ValueError:
                return None
        try:
            return float(stripped)
        except ValueError:
            return None

    if isinstance(value, (int, float)):
        if value > 1.0:
            return float(value) / 100.0
        return float(value)

    return None


def normalize_int(value: str | int | float | None) -> int | None:
    """Parse integer with missing sentinel handling.

    '33' -> 33, 33 -> 33, 33.0 -> 33
    '—'  -> None, None -> None, '' -> None
    """
    if value is None or value is MISSING:
        return None
    if isinstance(value, float) and value != value:  # NaN check
        return None
    if isinstance(value, (int, float)):
        return int(value)
    stripped = str(value).strip()
    if stripped in ("—", "-", "无", "未提及", "N/A", "n/a", "", "null"):
        return None
    try:
        return int(float(stripped))
    except (ValueError, TypeError):
        return None


# ═══ Field-Level Evidence ═══

@dataclass(frozen=True)
class ExtractedField:
    """Provenance record for a single parsed field.

    Enables calibration drift debugging — you can trace exactly
    where each number came from in the source document.

    Example:
        ExtractedField(
            field_path="market_facts.limit_up_count",
            value=46,
            unit="count",
            source_section="4. 大盘势能指标",
            evidence_text="涨停数 | 7.08 | 46",
            confidence=0.98,
            parser_rule="json_block:大盘势能",
        )
    """
    field_path: str           # "market_facts.limit_up_count"
    value: Any
    unit: str | None = None   # "count", "yi", "ratio", "board"
    source_section: str = ""  # "4. 大盘势能指标"
    evidence_text: str = ""   # "涨停数 | 7.08 | 46"
    confidence: float = 1.0   # 0.0–1.0
    parser_rule: str = ""     # "json_block:大盘势能" | "regex:board_table" | "table_row:theme"


# ═══ Extraction Quality Report ═══

@dataclass
class AnalystReferenceQuality:
    """Per-record extraction quality assessment.

    Consumers (CalibrationEngine, ReplayBenchmark, Frontend) MUST check
    extraction_status before treating any field as ground truth.
    """
    extraction_status: ExtractionStatus = ExtractionStatus.PARTIAL
    required_field_coverage: float = 0.0     # core fields found / core total
    optional_field_coverage: float = 0.0     # optional fields found / optional total
    missing_fields: tuple[str, ...] = ()
    low_confidence_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "extraction_status": self.extraction_status.value,
            "required_field_coverage": self.required_field_coverage,
            "optional_field_coverage": self.optional_field_coverage,
            "missing_fields": list(self.missing_fields),
            "low_confidence_fields": list(self.low_confidence_fields),
        }


# ═══ Core / Full Required Field Paths ═══

CORE_REQUIRED_FIELDS: tuple[str, ...] = (
    "market_facts.limit_up_count",
    "market_facts.max_board_height",
    "emotion_label.market_phase",
    "emotion_label.risk_level",
    "emotion_label.emotion_momentum",
)

FULL_REQUIRED_FIELDS: tuple[str, ...] = CORE_REQUIRED_FIELDS + (
    "relay_label.promotion_1_to_2",
    "relay_label.promotion_2_to_3",
    "strategy_label.allowed",
    "strategy_label.watch_points",
    "theme_lifecycle",
    "limitup_attribution",
    "leader_state",
)

OPTIONAL_FIELDS: tuple[str, ...] = (
    "market_facts.active_capital_yi",
    "market_facts.chain_board_count",
    "market_facts.market_up_ratio",
    "market_facts.loss_effect_ratio",
    "market_facts.composite_score",
    "emotion_label.cycle_score",
    "emotion_label.strategy",
    "relay_label.max_board_stock",
    "relay_label.first_board_success_rate",
    "relay_label.promotion_3_to_4",
    "relay_label.promotion_4_to_5",
    "relay_label.promotion_5_to_6",
    "relay_label.promotion_6_to_7",
    "strategy_label.forbidden",
    "strategy_label.summary",
    "external_env",
)


# ═══ Structured Data Layers ═══

@dataclass
class MarketFacts:
    """L0: Analyst-reported market facts."""
    limit_up_count: int | None = None
    chain_board_count: int | None = None
    max_board_height: int | None = None
    active_capital_yi: float | None = None      # 活跃资金（亿元）
    market_up_ratio: float | None = None         # 上涨比 (0-1)
    loss_effect_ratio: float | None = None       # 亏钱效应比
    composite_score: int | None = None           # 综合评分 (-10 to +10)
    down_below_minus5: int | None = None         # -5%以下个股数

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmotionLabel:
    """L1: Analyst emotion/phase assessment."""
    market_phase: str = ""                       # PANIC / FREEZE / REPAIR_WATCH / DISTRIBUTION / etc.
    risk_level: str = ""                         # LOW / MEDIUM / MEDIUM_HIGH / HIGH / CRITICAL
    emotion_momentum: float | None = None        # -18 ~ +10
    cycle_score: int | None = None               # running cycle score
    strategy: str = ""                           # analyst's strategy description

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RelayLabel:
    """L1: Analyst relay ecology data.

    All promotion rates stored as 0.0–1.0 ratios internally.
    Display layer converts to percentage.
    """
    max_board_height: int | None = None
    max_board_stock: str = ""
    first_board_success_rate: float | None = None  # 首板封板率
    promotion_1_to_2: float | None = None
    promotion_2_to_3: float | None = None
    promotion_3_to_4: float | None = None
    promotion_4_to_5: float | None = None
    promotion_5_to_6: float | None = None
    promotion_6_to_7: float | None = None

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThemeLifecycleEntry:
    """One theme's lifecycle state on a given date."""
    theme_name: str
    state: str                                   # 启动/调整/修复/观察/关注
    day_count: int = 0                           # 当前状态持续天数
    style: str = ""                              # institutional / hot_money / hybrid
    notes: str = ""


@dataclass
class LimitUpAttribution:
    """Limit-up stock classification by theme.

    key_stocks entries: [{code, name, board, time, reason, theme}]
    """
    theme_name: str
    board_heights: list[int] = field(default_factory=list)
    stock_count: int = 0
    key_stocks: list[dict[str, Any]] = field(default_factory=list)

    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class LeaderState:
    """Leader/high-board stock state."""
    stock_code: str
    stock_name: str
    board_height: int
    role: str = ""                               # market_leader / theme_leader / pioneer / follower / assistant_leader / 中军 / 补涨 / 穿越
    theme: str = ""
    death_type: str = ""                         # NONE / NORMAL / FRIED / LIMIT_DOWN / HEAVEN_EARTH
    board_str: str = ""                          # "7板" / "首板"


@dataclass
class StrategyLabel:
    """L3: Analyst strategy recommendations."""
    allowed: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    watch_points: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class ExternalEnvironment:
    """L6: External market context."""
    korea_index: dict[str, Any] = field(default_factory=dict)
    us_market: dict[str, Any] = field(default_factory=dict)
    key_events: list[str] = field(default_factory=list)


# ═══ Top-Level Record ═══

@dataclass
class AnalystReferenceRecord:
    """Complete analyst ground truth for a single trading day.

    This is the canonical format for analyst data ingestion.
    Fields that cannot be automatically extracted are tracked in
    quality.missing_fields and quality.low_confidence_fields.
    """
    trade_date: date
    source_type: str                             # pdf / markdown / manual / notion
    source_path: str = ""

    # ── Structured layers ──
    market_facts: MarketFacts = field(default_factory=MarketFacts)
    emotion_label: EmotionLabel = field(default_factory=EmotionLabel)
    relay_label: RelayLabel = field(default_factory=RelayLabel)
    theme_lifecycle: list[ThemeLifecycleEntry] = field(default_factory=list)
    limitup_attribution: list[LimitUpAttribution] = field(default_factory=list)
    leader_state: list[LeaderState] = field(default_factory=list)
    strategy_label: StrategyLabel = field(default_factory=StrategyLabel)
    external_env: ExternalEnvironment = field(default_factory=ExternalEnvironment)

    # ── Field-level provenance (Phase 4.1b) ──
    extracted_fields: list[ExtractedField] = field(default_factory=list)

    # ── Quality assessment (Phase 4.1b) ──
    quality: AnalystReferenceQuality = field(default_factory=AnalystReferenceQuality)

    # ── Legacy meta fields (kept for backward compat) ──
    confidence: float = 1.0
    extraction_status: str = ""
    needs_review_fields: list[str] = field(default_factory=list)
    raw_text: str = ""
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Methods ──

    def sync_legacy_fields(self) -> None:
        """Sync legacy flat fields from quality object for backward compat."""
        self.extraction_status = self.quality.extraction_status.value
        self.confidence = self.quality.required_field_coverage
        self.needs_review_fields = list(self.quality.missing_fields)

    def compute_quality(self) -> AnalystReferenceQuality:
        """Compute extraction quality from extracted fields and record state."""
        # Required coverage
        core_total = len(CORE_REQUIRED_FIELDS)
        core_found = sum(
            1 for fp in CORE_REQUIRED_FIELDS if self._field_has_value(fp)
        )
        req_coverage = core_found / core_total if core_total > 0 else 0.0

        # Optional coverage
        opt_total = len(OPTIONAL_FIELDS)
        opt_found = sum(
            1 for fp in OPTIONAL_FIELDS if self._field_has_value(fp)
        )
        opt_coverage = opt_found / opt_total if opt_total > 0 else 0.0

        # Missing fields
        missing: list[str] = []
        for fp in CORE_REQUIRED_FIELDS + FULL_REQUIRED_FIELDS:
            if not self._field_has_value(fp):
                missing.append(fp)

        # Low confidence fields
        low_conf = [
            ef.field_path for ef in self.extracted_fields
            if ef.confidence < 0.70
        ]

        # Derive status
        status = self._derive_status(core_found, core_total, opt_found, opt_total, missing)

        self.quality = AnalystReferenceQuality(
            extraction_status=status,
            required_field_coverage=round(req_coverage, 3),
            optional_field_coverage=round(opt_coverage, 3),
            missing_fields=tuple(missing),
            low_confidence_fields=tuple(low_conf),
        )
        return self.quality

    def _derive_status(
        self,
        core_found: int, core_total: int,
        opt_found: int, opt_total: int,
        missing: list[str],
    ) -> ExtractionStatus:
        if core_total == 0:
            return ExtractionStatus.FAILED
        core_ratio = core_found / core_total

        if core_ratio == 1.0:
            full_total = len(FULL_REQUIRED_FIELDS)
            full_found = sum(
                1 for fp in FULL_REQUIRED_FIELDS if self._field_has_value(fp)
            )
            full_ratio = full_found / full_total if full_total > 0 else 0.0
            if full_ratio >= 0.85:
                return ExtractionStatus.FULL_COMPLETE
            if full_ratio >= 0.5:
                # Core is complete but some full-required fields missing
                return ExtractionStatus.CORE_COMPLETE
            return ExtractionStatus.CORE_COMPLETE

        if core_ratio >= 0.6:
            return ExtractionStatus.PARTIAL

        if core_found >= 1:
            return ExtractionStatus.NEEDS_REVIEW

        return ExtractionStatus.FAILED

    def _field_has_value(self, field_path: str) -> bool:
        """Check if a dotted or named field path has a meaningful (non-missing) value."""
        try:
            # Collection fields
            if field_path == "theme_lifecycle":
                return len(self.theme_lifecycle) > 0
            if field_path == "limitup_attribution":
                return len(self.limitup_attribution) > 0
            if field_path == "leader_state":
                return len(self.leader_state) > 0
            if field_path == "external_env":
                return bool(
                    self.external_env.korea_index or
                    self.external_env.us_market or
                    self.external_env.key_events
                )

            # Dotted path: "market_facts.limit_up_count"
            parts = field_path.split(".")
            current: Any = self
            for part in parts:
                current = getattr(current, part, MISSING)
                if current is MISSING or current is None:
                    return False
            # At leaf
            if current is MISSING or current is None:
                return False
            if isinstance(current, str) and current == "":
                return False
            if isinstance(current, (list, tuple)) and len(current) == 0:
                return False
            return True
        except Exception:
            return False

    def get_field_value(self, field_path: str) -> Any:
        """Get field value by dotted path, returning MISSING if absent."""
        try:
            parts = field_path.split(".")
            current: Any = self
            for part in parts:
                current = getattr(current, part, MISSING)
                if current is MISSING:
                    return MISSING
            return current
        except Exception:
            return MISSING

    def to_db_dict(self) -> dict[str, Any]:
        import json
        return {
            "trade_date": self.trade_date,
            "source_type": self.source_type,
            "source_path": self.source_path,
            "market_facts": json.dumps(self.market_facts.__dict__, default=str),
            "emotion_label": json.dumps(self.emotion_label.__dict__, default=str),
            "relay_label": json.dumps(self.relay_label.__dict__, default=str),
            "theme_lifecycle": json.dumps([t.__dict__ for t in self.theme_lifecycle], default=str),
            "limitup_attribution": json.dumps([a.__dict__ for a in self.limitup_attribution], default=str),
            "leader_state": json.dumps([l.__dict__ for l in self.leader_state], default=str),
            "strategy_label": json.dumps(self.strategy_label.__dict__, default=str),
            "extraction_status": self.extraction_status,
            "needs_review_fields": self.needs_review_fields,
            "confidence": self.confidence,
            "raw_text": self.raw_text[:5000] if self.raw_text else "",
        }
