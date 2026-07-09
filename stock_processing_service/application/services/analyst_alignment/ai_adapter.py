"""Phase 4.2 — AI Reference View Adapter.

Converts MarketMetricsSnapshot (AI output) to AIDiagnosisReferenceView,
a structure isomorphic to AnalystReferenceRecord for comparison.

Design principle (per M2.5 canonical fact layer):
  adapt_metrics_only() — facts, relay, capital, leaders, emotion_momentum.
                         Does NOT fill market_phase / risk_level.
  adapt_with_diagnosis() — enriched with phase / risk / strategy / themes
                           from MarketDiagnosis and Narrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.application.services.analyst_reference.contracts import (
    EmotionLabel,
    LeaderState,
    LimitUpAttribution,
    MarketFacts,
    RelayLabel,
    StrategyLabel,
    ThemeLifecycleEntry,
)
from stock_processing_service.application.services.market_metrics.contracts import (
    LeaderEvolutionMetrics,
    LeaderSnapshot,
    MarketMetricsSnapshot,
)


ADAPTER_VERSION = "ai_adapter_v1"


# ═══ AI Reference View ═══

@dataclass(frozen=True)
class AIDiagnosisReferenceView:
    """AI diagnosis output in a structure isomorphic to AnalystReferenceRecord.

    This is the bridge between AI market metrics and analyst ground truth —
    both sides must use the same sub-object types for comparison to work.

    quality fields tell the Comparator:
      - which AI fields are missing
      - whether the adapter itself is confident
    """
    trade_date: date

    # Core layers — using the same classes as AnalystReferenceRecord
    market_facts: MarketFacts
    emotion_label: EmotionLabel
    relay_label: RelayLabel

    # Optional layers — best-effort from diagnosis / narrative
    theme_lifecycle: tuple[ThemeLifecycleEntry, ...] = ()
    limitup_attribution: tuple[LimitUpAttribution, ...] = ()
    leader_state: tuple[LeaderState, ...] = ()
    strategy_label: StrategyLabel = field(default_factory=StrategyLabel)

    # Provenance
    source_snapshot_ids: tuple[str, ...] = ()
    ai_module_versions: dict[str, str] = field(default_factory=dict)

    # Quality tracking (Phase 4.2 Comparator needs these)
    missing_fields: tuple[str, ...] = ()
    source_quality: float = 1.0            # 0–1, adapter confidence
    adapter_version: str = ADAPTER_VERSION

    @property
    def has_theme_data(self) -> bool:
        return len(self.theme_lifecycle) > 0

    @property
    def has_strategy_data(self) -> bool:
        return bool(self.strategy_label.allowed or self.strategy_label.summary)

    @property
    def has_phase_label(self) -> bool:
        return bool(self.emotion_label.market_phase)


# ═══ AI Adapter ═══

class AIAdapter:
    """Convert MarketMetricsSnapshot → AIDiagnosisReferenceView.

    Two-layer design:
      adapt_metrics_only()    — pure fact layer, no diagnosis
      adapt_with_diagnosis()  — enriched with phase/risk/strategy/themes
    """

    # ── Public API: metrics-only ──

    def adapt_metrics_only(
        self, snapshot: MarketMetricsSnapshot
    ) -> AIDiagnosisReferenceView:
        """Convert snapshot to analyst-comparable view — FACTS ONLY.

        market_phase / risk_level are left empty.
        Use adapt_with_diagnosis() for diagnosis-enriched conversion.
        """
        leaders = self._adapt_leaders(snapshot)
        relay, relay_missing = self._adapt_relay(snapshot, leaders)
        facts, facts_missing = self._adapt_facts(snapshot)

        missing = tuple(
            f"market_facts.{m}" for m in facts_missing
        ) + tuple(
            f"relay_label.{m}" for m in relay_missing
        )

        return AIDiagnosisReferenceView(
            trade_date=snapshot.trade_date,
            market_facts=facts,
            emotion_label=EmotionLabel(
                market_phase="",          # left empty — requires diagnosis
                risk_level="",            # left empty — requires diagnosis
                emotion_momentum=snapshot.emotion_momentum.momentum_raw,
            ),
            relay_label=relay,
            leader_state=leaders,
            theme_lifecycle=(),
            limitup_attribution=(),
            strategy_label=StrategyLabel(),
            source_snapshot_ids=(),
            missing_fields=missing,
            source_quality=1.0,
            adapter_version=ADAPTER_VERSION,
        )

    # ── Public API: diagnosis-enriched ──

    def adapt_with_diagnosis(
        self,
        snapshot: MarketMetricsSnapshot,
        diagnosis: dict[str, str] | None = None,
        narrative_themes: list[dict[str, Any]] | None = None,
        strategy_text: str | None = None,
    ) -> AIDiagnosisReferenceView:
        """Convert snapshot with diagnosis/narrative enrichment.

        diagnosis dict keys: phase_label, risk_label (from MarketDiagnosis)
        narrative_themes: list of {"theme_name", "state", "day_count", ...}
        strategy_text: free-text strategy summary from Narrative
        """
        base = self.adapt_metrics_only(snapshot)
        diag = diagnosis or {}

        # Enrich emotion with phase/risk from diagnosis
        emotion = EmotionLabel(
            market_phase=diag.get("phase_label", ""),
            risk_level=diag.get("risk_level", ""),
            emotion_momentum=base.emotion_label.emotion_momentum,
        )

        # Enrich themes from narrative
        themes = self._adapt_themes_from_narrative(narrative_themes or [])

        # Enrich strategy from narrative text
        strategy = self._adapt_strategy_from_text(strategy_text or "")

        # Track what's still missing after enrichment
        extra_missing = list(base.missing_fields)
        if not emotion.market_phase:
            extra_missing.append("emotion_label.market_phase")
        if not emotion.risk_level:
            extra_missing.append("emotion_label.risk_level")
        if not strategy_text:
            extra_missing.append("strategy_label")

        return AIDiagnosisReferenceView(
            trade_date=base.trade_date,
            market_facts=base.market_facts,
            emotion_label=emotion,
            relay_label=base.relay_label,
            leader_state=base.leader_state,
            theme_lifecycle=tuple(themes),
            limitup_attribution=(),
            strategy_label=strategy,
            source_snapshot_ids=base.source_snapshot_ids,
            missing_fields=tuple(extra_missing),
            source_quality=0.85 if diag else 0.60,
            adapter_version=ADAPTER_VERSION,
        )

    # ── Layer adapters (return value + missing field names) ──

    def _adapt_facts(
        self, s: MarketMetricsSnapshot
    ) -> tuple[MarketFacts, list[str]]:
        """Map AI breadth + limitup + capital + loss → MarketFacts.

        Source priority per the conversion table:
          chain_board_count: relay > limitup (deprecated)
          max_board_height:  relay > limitup
          active_capital_yi: capital.active_limitup_amount_yi
        """
        facts = MarketFacts()
        missing: list[str] = []

        # From breadth
        facts.market_up_ratio = s.breadth.up_ratio

        # From limitup
        facts.limit_up_count = s.limitup.total_count

        # chain_board_count: relay preferred, limitup fallback
        facts.chain_board_count = (
            s.relay.chain_board_count
            if hasattr(s.relay, "chain_board_count") and s.relay.chain_board_count
            else getattr(s.limitup, "chain_board_count", None)
        )

        # max_board_height: relay preferred, limitup fallback
        facts.max_board_height = (
            s.relay.max_board_height
            if hasattr(s.relay, "max_board_height") and s.relay.max_board_height
            else getattr(s.limitup, "max_board_height", None)
        )

        # From capital
        if hasattr(s.capital, "active_limitup_amount_yi"):
            facts.active_capital_yi = s.capital.active_limitup_amount_yi
        else:
            missing.append("active_capital_yi")

        # From loss effect
        if s.loss_effect is not None:
            facts.loss_effect_ratio = s.loss_effect.damage_ratio
        else:
            missing.append("loss_effect_ratio")

        # From high_position_death
        if s.high_position_death is not None:
            facts.composite_score = int(s.high_position_death.death_index)

        return facts, missing

    def _adapt_relay(
        self, s: MarketMetricsSnapshot, leaders: tuple[LeaderState, ...]
    ) -> tuple[RelayLabel, list[str]]:
        """Map AI relay ecology → RelayLabel.

        max_board_stock: derived from leader_evolution (highest board_height leader).
        RelayEcologyMetrics does NOT carry max_board_stock directly.
        """
        r = s.relay
        missing: list[str] = []

        # Derive max_board_stock from leaders
        max_stock = ""
        if leaders:
            max_leader = max(leaders, key=lambda l: l.board_height)
            max_stock = max_leader.stock_name

        if not max_stock:
            # Fallback: try getattr
            max_stock = getattr(r, "max_board_stock", "")

        relay = RelayLabel(
            max_board_height=r.max_board_height,
            max_board_stock=max_stock,
            first_board_success_rate=(
                getattr(r, "first_board_success_rate", None)
                if hasattr(r, "first_board_success_rate") else None
            ),
            promotion_1_to_2=r.promotion_1_to_2,
            promotion_2_to_3=r.promotion_2_to_3,
            promotion_3_to_4=(
                r.promotion_3_to_4 if hasattr(r, "promotion_3_to_4") else None
            ),
        )

        if not max_stock:
            missing.append("max_board_stock")

        return relay, missing

    def _adapt_leaders(
        self, s: MarketMetricsSnapshot
    ) -> tuple[LeaderState, ...]:
        """Map AI leader evolution → LeaderState tuple."""
        if s.leader_evolution is None:
            return ()

        leaders: list[LeaderState] = []
        for ls in s.leader_evolution.leaders:
            role = self._derive_leader_role(ls, s.leader_evolution)
            leaders.append(LeaderState(
                stock_code=ls.stock_code,
                stock_name=ls.stock_name,
                board_height=ls.board_height,
                role=role,
                theme=ls.theme_hint,
                death_type=ls.death_type,
            ))
        return tuple(leaders)

    def _adapt_themes_from_narrative(
        self, narrative_themes: list[dict[str, Any]]
    ) -> list[ThemeLifecycleEntry]:
        """Best-effort theme extraction from narrative engine output."""
        themes: list[ThemeLifecycleEntry] = []
        for nt in narrative_themes:
            theme_name = nt.get("theme_name", nt.get("name", ""))
            if not theme_name:
                continue
            state = nt.get("state", nt.get("phase", ""))
            day_count = nt.get("day_count", nt.get("days", 0))
            themes.append(ThemeLifecycleEntry(
                theme_name=str(theme_name),
                state=str(state),
                day_count=int(day_count) if day_count else 0,
            ))
        return themes

    def _adapt_strategy_from_text(self, text: str) -> StrategyLabel:
        """Best-effort strategy extraction from narrative text."""
        if not text:
            return StrategyLabel()
        return StrategyLabel(summary=text[:500])

    # ── Helpers ──

    def _derive_leader_role(
        self, ls: LeaderSnapshot, evo: LeaderEvolutionMetrics
    ) -> str:
        """Derive leader role from snapshot status and context."""
        status = ls.status
        if status in ("BREAK",):
            return "broken"
        if status in ("CROSS_OVER",):
            return "cross_over"
        if status in ("SUPER_CONTINUE",):
            return "market_leader"
        if status in ("NORMAL_CONTINUE",):
            if ls.board_height >= 5:
                return "market_leader"
            if ls.board_height >= 3:
                return "theme_leader"
            return "follower"
        if status in ("WEAKEN_UNEXPECTED",):
            return "weakened_leader"
        if status == "NEW":
            if ls.board_height >= 3:
                return "new_leader"
            return "pioneer"
        if status == "REPLACED":
            return "replaced"
        return ""
