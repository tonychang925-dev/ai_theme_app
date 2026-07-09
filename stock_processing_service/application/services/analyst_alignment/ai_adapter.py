"""Phase 4.2 — AI Reference View Adapter.

Converts MarketMetricsSnapshot (AI output) to AIDiagnosisReferenceView,
a structure isomorphic to AnalystReferenceRecord for comparison.
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
    LeaderSnapshot,
    LeaderEvolutionMetrics,
    MarketMetricsSnapshot,
)


# ═══ AI Reference View ═══

@dataclass(frozen=True)
class AIDiagnosisReferenceView:
    """AI diagnosis output in a structure isomorphic to AnalystReferenceRecord.

    This is the bridge between AI market metrics and analyst ground truth —
    both sides must use the same sub-object types for comparison to work.
    """
    trade_date: date

    # Core layers — using the same classes as AnalystReferenceRecord
    market_facts: MarketFacts
    emotion_label: EmotionLabel
    relay_label: RelayLabel

    # Optional layers — best-effort from narrative / engine outputs
    theme_lifecycle: tuple[ThemeLifecycleEntry, ...] = ()
    limitup_attribution: tuple[LimitUpAttribution, ...] = ()
    leader_state: tuple[LeaderState, ...] = ()
    strategy_label: StrategyLabel = field(default_factory=StrategyLabel)

    # Provenance
    source_snapshot_ids: tuple[str, ...] = ()
    ai_module_versions: dict[str, str] = field(default_factory=dict)

    @property
    def has_theme_data(self) -> bool:
        return len(self.theme_lifecycle) > 0

    @property
    def has_strategy_data(self) -> bool:
        return bool(self.strategy_label.allowed or self.strategy_label.summary)


# ═══ AI Adapter ═══

class AIAdapter:
    """Convert MarketMetricsSnapshot → AIDiagnosisReferenceView.

    Mapping rules:
      MarketBreadthMetrics  + LimitUpMetrics  → MarketFacts
      EmotionMomentumMetrics                   → EmotionLabel
      RelayEcologyMetrics                      → RelayLabel
      LeaderEvolutionMetrics                   → LeaderState[]
      ActiveCapitalMetrics                     → MarketFacts.active_capital_yi
      LossEffectMetrics                        → MarketFacts.loss_effect_ratio
    """

    # ── Public API ──

    def adapt(
        self,
        snapshot: MarketMetricsSnapshot,
        diagnosis: dict[str, str] | None = None,
    ) -> AIDiagnosisReferenceView:
        """Convert a MarketMetricsSnapshot to analyst-comparable view.

        diagnosis dict provides phase_label/risk_level that are not in
        EmotionMomentumMetrics itself but are computed by MarketDiagnosis.
        Example: {"phase_label": "PANIC", "risk_level": "HIGH"}
        """
        diagnosis = diagnosis or {}
        return AIDiagnosisReferenceView(
            trade_date=snapshot.trade_date,
            market_facts=self._adapt_facts(snapshot),
            emotion_label=self._adapt_emotion(snapshot, diagnosis),
            relay_label=self._adapt_relay(snapshot),
            leader_state=self._adapt_leaders(snapshot),
            theme_lifecycle=(),
            limitup_attribution=(),
            strategy_label=StrategyLabel(),
            source_snapshot_ids=(),
        )

    def adapt_with_narrative(
        self,
        snapshot: MarketMetricsSnapshot,
        narrative_themes: list[dict[str, Any]] | None = None,
        strategy_text: str | None = None,
        diagnosis: dict[str, str] | None = None,
    ) -> AIDiagnosisReferenceView:
        """Extended conversion with narrative enrichment for themes/strategy."""
        view = self.adapt(snapshot, diagnosis=diagnosis)

        # Enrich themes from narrative output
        themes = self._adapt_themes_from_narrative(narrative_themes or [])
        strategy = self._adapt_strategy_from_text(strategy_text or "")

        return AIDiagnosisReferenceView(
            trade_date=view.trade_date,
            market_facts=view.market_facts,
            emotion_label=view.emotion_label,
            relay_label=view.relay_label,
            leader_state=view.leader_state,
            theme_lifecycle=tuple(themes),
            limitup_attribution=(),
            strategy_label=strategy,
            source_snapshot_ids=view.source_snapshot_ids,
        )

    # ── Layer adapters ──

    def _adapt_facts(self, s: MarketMetricsSnapshot) -> MarketFacts:
        """Map AI breadth + limitup + capital + loss → MarketFacts."""
        facts = MarketFacts()

        # From breadth
        facts.market_up_ratio = s.breadth.up_ratio
        # breadth.limit_up_count is per breadth metrics (may differ from limitup module)
        # Prefer limitup module for limit_up count

        # From limitup (preferred source for limit-up data)
        facts.limit_up_count = s.limitup.total_count
        facts.chain_board_count = s.limitup.chain_board_count
        facts.max_board_height = s.limitup.max_board_height

        # From capital: active_limitup_amount_yi is the 涨停活跃资金 in 亿元
        facts.active_capital_yi = s.capital.active_limitup_amount_yi

        # From loss effect (if available)
        if s.loss_effect is not None:
            facts.loss_effect_ratio = s.loss_effect.damage_ratio

        # From high_position_death (if available)
        if s.high_position_death is not None:
            facts.composite_score = int(s.high_position_death.death_index)

        return facts

    def _adapt_emotion(
        self, s: MarketMetricsSnapshot, diagnosis: dict[str, str]
    ) -> EmotionLabel:
        """Map AI emotion momentum → EmotionLabel.

        EmotionMomentumMetrics carries raw momentum scores.
        phase_label / risk_level come from MarketDiagnosis (or diagnosis dict).
        """
        em = s.emotion_momentum
        return EmotionLabel(
            market_phase=diagnosis.get("phase_label", ""),
            risk_level=diagnosis.get("risk_level", ""),
            emotion_momentum=em.momentum_raw,
            cycle_score=None,
            strategy="",
        )

    def _adapt_relay(self, s: MarketMetricsSnapshot) -> RelayLabel:
        """Map AI relay ecology → RelayLabel.

        RelayEcologyMetrics has promotion rates and board heights.
        max_board_stock is NOT in RelayEcologyMetrics — stays empty.
        """
        r = s.relay
        return RelayLabel(
            max_board_height=r.max_board_height,
            max_board_stock="",
            first_board_success_rate=None,
            promotion_1_to_2=r.promotion_1_to_2,
            promotion_2_to_3=r.promotion_2_to_3,
            promotion_3_to_4=r.promotion_3_to_4 if hasattr(r, "promotion_3_to_4") else None,
        )

    def _adapt_leaders(self, s: MarketMetricsSnapshot) -> tuple[LeaderState, ...]:
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
