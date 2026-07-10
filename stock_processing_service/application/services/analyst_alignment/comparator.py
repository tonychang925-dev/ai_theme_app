"""Phase 4.2 T03 — Analyst Comparator.

Core comparison engine: AnalystReferenceRecord vs AIDiagnosisReferenceView.
Produces AnalystAlignmentReport with MetricDiff, SemanticDiff, and
missing/conflict-aware scoring.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from stock_processing_service.application.services.analyst_reference.contracts import (
    AnalystReferenceQuality,
    AnalystReferenceRecord,
    EmotionLabel,
    MarketFacts,
    RelayLabel,
    StrategyLabel,
)
from stock_processing_service.application.services.analyst_alignment.ai_adapter import (
    AIDiagnosisReferenceView,
)
from stock_processing_service.application.services.analyst_alignment.contracts import (
    AnalystAlignmentReport,
    DiffType,
    ErrorType,
    MatchType,
    MetricDiff,
    SemanticDiff,
)


# ═══ Phase Compatibility Matrix ═══
# (phase_a, phase_b) → score. Symmetric — entries are normalized form (lower, higher).

_PHASE_COMPATIBLE: dict[tuple[str, str], float] = {
    ("PANIC", "FREEZE"): 0.8,
    ("PANIC", "REPAIR_WATCH"): 0.5,
    ("PANIC", "WEAK_REPAIR"): 0.4,
    ("FREEZE", "REPAIR_WATCH"): 0.6,
    ("FREEZE", "WEAK_REPAIR"): 0.5,
    ("REPAIR_WATCH", "WEAK_REPAIR"): 0.8,
    ("REPAIR_WATCH", "REBOUND"): 0.6,
    ("REPAIR_WATCH", "DISTRIBUTION"): 0.4,
    ("WEAK_REPAIR", "REBOUND"): 0.6,
    ("CLIMAX", "ACCELERATION"): 0.6,
    ("CLIMAX", "DISTRIBUTION"): 0.5,
    ("DISTRIBUTION", "FIRST_DIVERGENCE"): 0.7,
    ("DISTRIBUTION", "FADE"): 0.5,
    ("ICE_POINT", "PANIC"): 0.8,
    ("ICE_POINT", "FREEZE"): 0.7,
    ("REBOUND", "SECOND_WAVE"): 0.5,
    ("ACCELERATION", "REBOUND"): 0.4,
    ("ACCELERATION", "FIRST_DIVERGENCE"): 0.5,
    ("CHAOS", "FIRST_DIVERGENCE"): 0.65,
    ("CHAOS", "DISTRIBUTION"): 0.45,
    ("CHAOS", "FADE"): 0.5,
    ("CHAOS", "WEAK_REPAIR"): 0.55,
    ("CHAOS", "REPAIR_WATCH"): 0.50,
    ("FADE", "FIRST_DIVERGENCE"): 0.5,
}


# ═══ Risk Level Order ═══

_RISK_ORDER: tuple[str, ...] = ("LOW", "MEDIUM", "MEDIUM_HIGH", "HIGH", "CRITICAL")


# ═══ Facts Tolerance Table ═══

_FACTS_TOLERANCE: dict[str, tuple[float, float]] = {
    # field_path → (absolute_tolerance, pct_tolerance)
    "market_facts.limit_up_count": (1, 0.0),
    "market_facts.chain_board_count": (1, 0.0),
    "market_facts.max_board_height": (0, 0.0),            # strict — core ecology
    "market_facts.active_capital_yi": (20, 0.05),          # ±20亿 or ±5%
    "market_facts.market_up_ratio": (0.03, 0.0),
    "market_facts.loss_effect_ratio": (0.05, 0.05),
}

# Fields that adapt_metrics_only() can't provide — never penalize AI for these
_METRICS_ONLY_MISSING: frozenset[str] = frozenset({
    "emotion_label.market_phase",
    "emotion_label.risk_level",
    "strategy_label",
    "strategy_label.allowed",
    "strategy_label.forbidden",
    "strategy_label.watch_points",
})



# ═══ AnalystComparator ═══

class AnalystComparator:
    """Compare AnalystReferenceRecord ↔ AIDiagnosisReferenceView.

    Produces AnalystAlignmentReport with per-category scores,
    missing/conflict handling, and phase/risk semantic matching.

    Usage:
        comparator = AnalystComparator()
        report = comparator.compare(analyst_record, ai_view)
    """

    def compare(
        self,
        analyst: AnalystReferenceRecord,
        ai: AIDiagnosisReferenceView,
    ) -> AnalystAlignmentReport:
        """Full comparison of analyst vs AI for one trading day."""
        assert analyst.trade_date == ai.trade_date, \
            f"Trade date mismatch: {analyst.trade_date} vs {ai.trade_date}"

        aq = analyst.quality
        ai_missing = set(ai.missing_fields)
        ref_conflicts = set(aq.low_confidence_fields)

        # Per-category comparisons
        fact_diffs = self.compare_facts(
            analyst.market_facts, ai.market_facts, aq, ai_missing, ref_conflicts)
        relay_diffs = self.compare_relay(
            analyst.relay_label, ai.relay_label, aq, ai_missing, ref_conflicts)
        emotion_diffs = self.compare_emotion(
            analyst.emotion_label, ai.emotion_label, ai)
        strategy_diffs = self.compare_strategy(
            analyst.strategy_label, ai.strategy_label, ai)
        leader_diffs = self.compare_leaders(analyst, ai)
        theme_diffs = self.compare_themes(analyst, ai)

        # Per-category scores
        facts_score = self._aggregate_score(fact_diffs)
        relay_score = self._aggregate_score(relay_diffs)
        emotion_score = self._aggregate_score(emotion_diffs)
        strategy_score = self._aggregate_score(strategy_diffs)
        leader_score = self._aggregate_score(leader_diffs)
        theme_score = self._aggregate_score(theme_diffs)

        # T03 temp formula
        overall_score = (
            0.30 * facts_score
            + 0.25 * emotion_score
            + 0.20 * relay_score
            + 0.10 * strategy_score
            + 0.10 * theme_score
            + 0.05 * leader_score
        )

        # Collect errors
        errors = self._classify_errors(fact_diffs, relay_diffs, emotion_diffs,
                                        strategy_diffs, leader_diffs)
        excluded = self._collect_excluded(fact_diffs, relay_diffs, emotion_diffs,
                                           strategy_diffs, leader_diffs, theme_diffs)
        drifts = self._collect_major_drifts(fact_diffs, relay_diffs, emotion_diffs)

        return AnalystAlignmentReport(
            trade_date=analyst.trade_date,
            fact_diffs=fact_diffs,
            relay_diffs=relay_diffs,
            emotion_diffs=emotion_diffs,
            strategy_diffs=strategy_diffs,
            theme_diffs=theme_diffs,
            leader_diffs=leader_diffs,
            facts_score=facts_score,
            relay_score=relay_score,
            emotion_score=emotion_score,
            strategy_score=strategy_score,
            theme_score=theme_score,
            leader_score=leader_score,
            overall_score=overall_score,
            error_types=tuple(errors),
            excluded_fields=tuple(excluded),
            major_drifts=tuple(drifts),
            analyst_quality=aq.required_field_coverage,
            ai_quality=ai.source_quality,
        )

    # ── Facts ──

    def compare_facts(
        self,
        analyst: MarketFacts,
        ai: MarketFacts,
        aq: AnalystReferenceQuality,
        ai_missing: set[str],
        ref_conflicts: set[str],
    ) -> tuple[MetricDiff, ...]:
        diffs: list[MetricDiff] = []
        fields = [
            ("market_facts.limit_up_count", analyst.limit_up_count, ai.limit_up_count),
            ("market_facts.chain_board_count", analyst.chain_board_count, ai.chain_board_count),
            ("market_facts.max_board_height", analyst.max_board_height, ai.max_board_height),
            ("market_facts.active_capital_yi", analyst.active_capital_yi, ai.active_capital_yi),
            ("market_facts.market_up_ratio", analyst.market_up_ratio, ai.market_up_ratio),
            ("market_facts.loss_effect_ratio", analyst.loss_effect_ratio, ai.loss_effect_ratio),
        ]
        for field_path, a_val, ai_val in fields:
            tol_abs, tol_pct = _FACTS_TOLERANCE.get(field_path, (0.0, 0.0))
            diff = self._compare_numeric(field_path, a_val, ai_val,
                                          tol_abs, tol_pct,
                                          aq, ai_missing, ref_conflicts)
            diffs.append(diff)
        return tuple(diffs)

    # ── Relay ──

    def compare_relay(
        self,
        analyst: RelayLabel,
        ai: RelayLabel,
        aq: AnalystReferenceQuality,
        ai_missing: set[str],
        ref_conflicts: set[str],
    ) -> tuple[MetricDiff, ...]:
        diffs: list[MetricDiff] = []
        fields = [
            ("relay_label.max_board_height", analyst.max_board_height, ai.max_board_height),
            ("relay_label.promotion_1_to_2", analyst.promotion_1_to_2, ai.promotion_1_to_2),
            ("relay_label.promotion_2_to_3", analyst.promotion_2_to_3, ai.promotion_2_to_3),
        ]
        # Tolerance: max_board strict, promotion rates ±0.02 or 20%
        tolerances = {
            "relay_label.max_board_height": (0, 0.0),
            "relay_label.promotion_1_to_2": (0.02, 0.20),
            "relay_label.promotion_2_to_3": (0.02, 0.20),
        }
        for field_path, a_val, ai_val in fields:
            tol_abs, tol_pct = tolerances.get(field_path, (0.0, 0.0))
            diff = self._compare_numeric(field_path, a_val, ai_val,
                                          tol_abs, tol_pct,
                                          aq, ai_missing, ref_conflicts)
            diffs.append(diff)
        return tuple(diffs)

    # ── Emotion ──

    def compare_emotion(
        self,
        analyst: EmotionLabel,
        ai: EmotionLabel,
        ai_view: AIDiagnosisReferenceView,
    ) -> tuple[SemanticDiff | MetricDiff, ...]:
        diffs: list[SemanticDiff | MetricDiff] = []

        # market_phase — semantic comparison
        diffs.append(self._compare_phase(analyst.market_phase, ai.market_phase, ai_view))

        # risk_level — ordinal comparison
        diffs.append(self._compare_risk(analyst.risk_level, ai.risk_level, ai_view))

        # emotion_momentum — numeric with tolerance
        a_mom = analyst.emotion_momentum
        ai_mom = ai.emotion_momentum
        diffs.append(self._compare_numeric(
            "emotion_label.emotion_momentum", a_mom, ai_mom,
            tol_abs=3.0, tol_pct=0.0,
            analyst_quality=AnalystReferenceQuality(),
            ai_missing=set(ai_view.missing_fields),
            ref_conflicts=set(),
        ))

        return tuple(diffs)

    # ── Strategy ──

    def compare_strategy(
        self,
        analyst: StrategyLabel,
        ai: StrategyLabel,
        ai_view: AIDiagnosisReferenceView,
    ) -> tuple[SemanticDiff, ...]:
        diffs: list[SemanticDiff] = []

        # Strategy summary — keyword overlap
        a_text = analyst.summary or " ".join(analyst.allowed + analyst.forbidden + analyst.watch_points)
        ai_text = ai.summary
        diffs.append(self._compare_strategy_text(a_text, ai_text, ai_view))

        return tuple(diffs)

    # ── Leaders ──

    def compare_leaders(
        self,
        analyst: AnalystReferenceRecord,
        ai: AIDiagnosisReferenceView,
    ) -> tuple[SemanticDiff, ...]:
        diffs: list[SemanticDiff] = []

        a_leaders = {l.stock_code for l in analyst.leader_state}
        ai_leaders = {l.stock_code for l in ai.leader_state}

        if not a_leaders and not ai_leaders:
            diffs.append(SemanticDiff(
                field_path="leader_state", analyst_label="", ai_label="",
                match_type=MatchType.EXACT, score=1.0, reason="Both empty",
            ))
        elif not a_leaders:
            diffs.append(SemanticDiff(
                field_path="leader_state", analyst_label="", ai_label=str(ai_leaders),
                match_type=MatchType.MISSING, score=0.5, reason="Analyst leader data missing",
                diff_type=DiffType.MISSING_ANALYST, excluded_from_score=True,
            ))
        elif not ai_leaders:
            diffs.append(SemanticDiff(
                field_path="leader_state", analyst_label=str(a_leaders), ai_label="",
                match_type=MatchType.MISSING, score=0.0, reason="AI leader data missing",
            ))
        else:
            overlap = a_leaders & ai_leaders
            score = len(overlap) / max(len(a_leaders), len(ai_leaders))
            match_type = MatchType.EXACT if score >= 0.9 else MatchType.COMPATIBLE if score >= 0.5 else MatchType.NEAR_MISS
            diffs.append(SemanticDiff(
                field_path="leader_state",
                analyst_label=f"{len(a_leaders)} leaders: {sorted(a_leaders)[:5]}",
                ai_label=f"{len(ai_leaders)} leaders: {sorted(ai_leaders)[:5]}",
                match_type=match_type, score=round(score, 3),
                reason=f"Overlap: {len(overlap)}/{max(len(a_leaders), len(ai_leaders))}",
            ))

        return tuple(diffs)

    # ── Themes (lightweight Jaccard) ──

    def compare_themes(
        self,
        analyst: AnalystReferenceRecord,
        ai: AIDiagnosisReferenceView,
    ) -> tuple[SemanticDiff, ...]:
        diffs: list[SemanticDiff] = []

        a_names = {t.theme_name for t in analyst.theme_lifecycle}
        ai_names = {t.theme_name for t in ai.theme_lifecycle}

        if not a_names and not ai_names:
            diffs.append(SemanticDiff(
                field_path="theme_lifecycle", analyst_label="", ai_label="",
                match_type=MatchType.EXACT, score=1.0, reason="Both empty",
            ))
        elif not a_names:
            diffs.append(SemanticDiff(
                field_path="theme_lifecycle", analyst_label="", ai_label=str(ai_names),
                match_type=MatchType.MISSING, score=0.5, reason="Analyst theme data missing",
                diff_type=DiffType.MISSING_ANALYST, excluded_from_score=True,
            ))
        elif not ai_names:
            diffs.append(SemanticDiff(
                field_path="theme_lifecycle", analyst_label=str(a_names), ai_label="",
                match_type=MatchType.MISSING, score=0.0, reason="AI theme data missing",
            ))
        else:
            # Use ThemeAliasResolver for normalized matching
            from .theme_alias import ThemeAliasResolver
            resolver = ThemeAliasResolver()
            score, detail = resolver.compare(a_names, ai_names)
            match_type = (
                MatchType.EXACT if score >= 0.8
                else MatchType.COMPATIBLE if score >= 0.4
                else MatchType.NEAR_MISS
            )
            diffs.append(SemanticDiff(
                field_path="theme_lifecycle",
                analyst_label=f"{len(a_names)} themes, canonical={detail.get('analyst_canonical', [])[:5]}",
                ai_label=f"{len(ai_names)} themes, canonical={detail.get('ai_canonical', [])[:5]}",
                match_type=match_type, score=score,
                reason=f"Alias-normalized Jaccard={detail.get('jaccard', 0):.2f} industry={detail.get('industry_match', 0):.2f}",
            ))

        return tuple(diffs)

    # ── Numeric comparator ──

    def _compare_numeric(
        self,
        field_path: str,
        analyst_val: object | None,
        ai_val: object | None,
        tol_abs: float,
        tol_pct: float,
        analyst_quality: AnalystReferenceQuality,
        ai_missing: set[str],
        ref_conflicts: set[str],
    ) -> MetricDiff:
        """Compare two numeric values with tolerance and missing/conflict handling."""

        # Reference missing
        if analyst_val is None:
            return MetricDiff(
                field_path=field_path, analyst_value=None, ai_value=ai_val,
                diff_type=DiffType.MISSING_ANALYST,
                excluded_from_score=True,
                reason="Analyst reference field missing",
                analyst_confidence=0.0, ai_confidence=1.0,
            )

        # AI missing
        if ai_val is None:
            # Check if it's metrics-only mode and this field is not available
            if field_path in _METRICS_ONLY_MISSING:
                return MetricDiff(
                    field_path=field_path, analyst_value=analyst_val, ai_value=None,
                    diff_type=DiffType.MISSING_AI,
                    excluded_from_score=True,
                    reason="metrics_only mode: field requires diagnosis enrichment",
                    analyst_confidence=analyst_quality.required_field_coverage,
                    ai_confidence=0.0,
                )
            return MetricDiff(
                field_path=field_path, analyst_value=analyst_val, ai_value=None,
                diff_type=DiffType.MISSING_AI,
                score=0.0, passed=False,
                reason="AI field missing",
                analyst_confidence=analyst_quality.required_field_coverage,
                ai_confidence=0.0,
            )

        # Reference conflict
        if field_path in ref_conflicts:
            return MetricDiff(
                field_path=field_path, analyst_value=analyst_val, ai_value=ai_val,
                diff_type=DiffType.REFERENCE_CONFLICT,
                excluded_from_score=True,
                reason="Analyst reference has conflicting sources",
                analyst_confidence=0.5, ai_confidence=1.0,
                weight=0.5,
            )

        # Numeric comparison
        try:
            a_num = float(analyst_val)  # type: ignore[arg-type]
            b_num = float(ai_val)       # type: ignore[arg-type]
        except (TypeError, ValueError):
            return MetricDiff(
                field_path=field_path, analyst_value=analyst_val, ai_value=ai_val,
                diff_type=DiffType.LABEL_DIFF,
                reason=f"Non-numeric values: {analyst_val} vs {ai_val}",
            )

        abs_diff = abs(a_num - b_num)
        rel_diff = abs_diff / max(abs(a_num), 1e-6)

        # Combined tolerance: satisfy EITHER abs OR pct (business semantics: "±X or ±Y%")
        if tol_abs > 0 or tol_pct > 0:
            passed_checks: list[bool] = []
            if tol_abs > 0:
                passed_checks.append(abs_diff <= tol_abs)
            if tol_pct > 0:
                passed_checks.append(rel_diff <= tol_pct)
            passed = any(passed_checks) if passed_checks else abs_diff == 0
        else:
            passed = abs_diff == 0

        # Score: 1.0 for exact, linear decay within tolerance, 0.4 below
        if passed:
            if abs_diff == 0:
                score = 1.0
            else:
                # Within tolerance but not exact — score proportionally
                max_tol_factor = max(
                    abs_diff / max(tol_abs, 1e-6) if tol_abs > 0 else 0,
                    rel_diff / max(tol_pct, 1e-6) if tol_pct > 0 else 0,
                )
                score = max(0.6, 1.0 - 0.4 * min(max_tol_factor, 1.0))
        else:
            # Outside tolerance — partial credit
            score = max(0.1, 0.6 - 0.3 * min(abs_diff / max(tol_abs * 2, 1.0), 1.0))

        return MetricDiff(
            field_path=field_path,
            analyst_value=analyst_val, ai_value=ai_val,
            diff_type=DiffType.EXACT_MATCH if passed and abs_diff == 0 else DiffType.NUMERIC_DIFF,
            absolute_diff=round(abs_diff, 4),
            relative_diff=round(rel_diff, 4),
            passed=passed,
            score=round(score, 3),
            tolerance=tol_abs,
            tolerance_pct=tol_pct,
            analyst_confidence=analyst_quality.required_field_coverage,
            ai_confidence=1.0,
        )

    # ── Phase comparator ──

    def _compare_phase(
        self, analyst_phase: str, ai_phase: str, ai_view: AIDiagnosisReferenceView
    ) -> SemanticDiff:
        """Compare market phase labels with compatibility matrix."""

        # Missing AI phase (metrics_only)
        if not ai_phase:
            if not ai_view.has_phase_label:
                return SemanticDiff(
                    field_path="emotion_label.market_phase",
                    analyst_label=analyst_phase, ai_label="",
                    match_type=MatchType.MISSING,
                    score=0.5,  # neutral — can't compare
                    reason="AI phase not available (metrics_only mode)",
                    diff_type=DiffType.MISSING_AI,
                    excluded_from_score=True,
                )
            return SemanticDiff(
                field_path="emotion_label.market_phase",
                analyst_label=analyst_phase, ai_label="",
                match_type=MatchType.MISSING,
                score=0.0,
                reason="AI phase missing",
            )

        # Missing analyst phase
        if not analyst_phase:
            return SemanticDiff(
                field_path="emotion_label.market_phase",
                analyst_label="", ai_label=ai_phase,
                match_type=MatchType.MISSING,
                score=0.5,
                reason="Analyst phase missing",
                diff_type=DiffType.MISSING_ANALYST,
                excluded_from_score=True,
            )

        # Exact match
        a_norm = analyst_phase.strip().upper()
        b_norm = ai_phase.strip().upper()
        if a_norm == b_norm:
            return SemanticDiff(
                field_path="emotion_label.market_phase",
                analyst_label=analyst_phase, ai_label=ai_phase,
                match_type=MatchType.EXACT, score=1.0,
                reason="Exact phase match",
            )

        # Compatibility matrix lookup
        key = tuple(sorted([a_norm, b_norm]))
        compat_score = _PHASE_COMPATIBLE.get(key, 0.0)

        if compat_score >= 0.7:
            match_type = MatchType.COMPATIBLE
        elif compat_score >= 0.4:
            match_type = MatchType.NEAR_MISS
        else:
            match_type = MatchType.OPPOSITE

        return SemanticDiff(
            field_path="emotion_label.market_phase",
            analyst_label=analyst_phase, ai_label=ai_phase,
            match_type=match_type, score=compat_score,
            reason=f"Phase mismatch: {analyst_phase} vs {ai_phase}",
        )

    # ── Risk comparator ──

    def _compare_risk(
        self, analyst_risk: str, ai_risk: str, ai_view: AIDiagnosisReferenceView
    ) -> SemanticDiff:
        """Compare risk levels with ordinal distance."""

        # Missing AI risk
        if not ai_risk:
            if not ai_view.has_phase_label:
                return SemanticDiff(
                    field_path="emotion_label.risk_level",
                    analyst_label=analyst_risk, ai_label="",
                    match_type=MatchType.MISSING,
                    score=0.5,
                    reason="AI risk not available (metrics_only mode)",
                    diff_type=DiffType.MISSING_AI,
                    excluded_from_score=True,
                )
            return SemanticDiff(
                field_path="emotion_label.risk_level",
                analyst_label=analyst_risk, ai_label="",
                match_type=MatchType.MISSING,
                score=0.0,
                reason="AI risk missing",
            )

        if not analyst_risk:
            return SemanticDiff(
                field_path="emotion_label.risk_level",
                analyst_label="", ai_label=ai_risk,
                match_type=MatchType.MISSING,
                score=0.5,
                reason="Analyst risk missing",
                diff_type=DiffType.MISSING_ANALYST,
                excluded_from_score=True,
            )

        # Exact match
        a_norm = analyst_risk.strip().upper()
        b_norm = ai_risk.strip().upper()
        if a_norm == b_norm:
            return SemanticDiff(
                field_path="emotion_label.risk_level",
                analyst_label=analyst_risk, ai_label=ai_risk,
                match_type=MatchType.EXACT, score=1.0,
                reason="Exact risk match",
            )

        # Ordinal distance
        try:
            a_idx = _RISK_ORDER.index(a_norm)
            b_idx = _RISK_ORDER.index(b_norm)
            distance = abs(a_idx - b_idx)
        except ValueError:
            return SemanticDiff(
                field_path="emotion_label.risk_level",
                analyst_label=analyst_risk, ai_label=ai_risk,
                match_type=MatchType.NEAR_MISS, score=0.5,
                reason=f"Unknown risk level: {analyst_risk} vs {ai_risk}",
            )

        if distance == 1:
            score = 0.75
            match_type = MatchType.COMPATIBLE
        elif distance == 2:
            score = 0.4
            match_type = MatchType.NEAR_MISS
        else:
            score = 0.0
            match_type = MatchType.OPPOSITE

        return SemanticDiff(
            field_path="emotion_label.risk_level",
            analyst_label=analyst_risk, ai_label=ai_risk,
            match_type=match_type, score=score,
            reason=f"Risk distance={distance}: {analyst_risk} vs {ai_risk}",
        )

    # ── Strategy intent comparator ──

    def _compare_strategy_text(
        self, a_text: str, ai_text: str, ai_view: AIDiagnosisReferenceView
    ) -> SemanticDiff:
        """Strategy intent matching via StrategyIntentMatcher (v1).

        Replaces keyword overlap with 8-label intent extraction + recall-weighted scoring.
        """

        if not ai_text:
            if not ai_view.has_strategy_data:
                return SemanticDiff(
                    field_path="strategy_label",
                    analyst_label=a_text[:100], ai_label="",
                    match_type=MatchType.MISSING,
                    score=0.5,
                    reason="AI strategy not available (metrics_only)",
                    diff_type=DiffType.MISSING_AI,
                    excluded_from_score=True,
                )
            return SemanticDiff(
                field_path="strategy_label",
                analyst_label=a_text[:100], ai_label="",
                match_type=MatchType.MISSING,
                score=0.0,
                reason="AI strategy missing",
            )

        if not a_text:
            return SemanticDiff(
                field_path="strategy_label",
                analyst_label="", ai_label=ai_text[:100],
                match_type=MatchType.MISSING,
                score=0.5,
                reason="Analyst strategy missing",
                diff_type=DiffType.MISSING_ANALYST,
                excluded_from_score=True,
            )

        # Use StrategyIntentMatcher
        from .strategy_intent import StrategyIntentMatcher
        matcher = StrategyIntentMatcher()
        match = matcher.compare(a_text, ai_text)

        score = match.score
        if score >= 0.85:
            match_type = MatchType.EXACT
        elif score >= 0.65:
            match_type = MatchType.COMPATIBLE
        elif score >= 0.35:
            match_type = MatchType.NEAR_MISS
        else:
            match_type = MatchType.OPPOSITE

        return SemanticDiff(
            field_path="strategy_label",
            analyst_label=f"intents={match.analyst_intents}",
            ai_label=f"intents={match.ai_intents}",
            match_type=match_type, score=round(score, 3),
            reason=match.reason,
        )

    # ── Score aggregation ──

    def _aggregate_score(self, diffs: tuple[MetricDiff | SemanticDiff, ...]) -> float:
        """Weighted average of included diffs."""
        total_weight = 0.0
        weighted_sum = 0.0
        for d in diffs:
            if d.excluded_from_score:
                continue
            weight = getattr(d, "weight", 1.0)
            total_weight += weight
            weighted_sum += d.score * weight
        return weighted_sum / max(total_weight, 1e-6)

    # ── Error classification ──

    def _classify_errors(
        self,
        facts: tuple[MetricDiff, ...],
        relay: tuple[MetricDiff, ...],
        emotion: tuple[SemanticDiff | MetricDiff, ...],
        strategy: tuple[SemanticDiff, ...],
        leaders: tuple[SemanticDiff, ...],
    ) -> list[str]:
        errors: list[str] = []
        all_diffs = tuple(facts) + tuple(relay) + tuple(emotion) + tuple(strategy) + tuple(leaders)

        for d in all_diffs:
            if d.excluded_from_score:
                continue
            if isinstance(d, MetricDiff):
                if d.diff_type == DiffType.MISSING_AI and not d.excluded_from_score:
                    errors.append(ErrorType.DATA_ERROR)
                elif d.diff_type == DiffType.NUMERIC_DIFF:
                    if d.absolute_diff is not None and d.absolute_diff > (d.tolerance * 3 if d.tolerance > 0 else 0):
                        errors.append(ErrorType.DATA_ERROR)
            elif isinstance(d, SemanticDiff):
                if d.match_type == MatchType.OPPOSITE:
                    if "emotion_label" in d.field_path:
                        errors.append(ErrorType.SEMANTIC_ERROR)
                    elif "strategy" in d.field_path:
                        errors.append(ErrorType.STRATEGY_ERROR)

        # Deduplicate
        return sorted(set(errors))

    def _collect_excluded(
        self, *diff_tuples: tuple[MetricDiff | SemanticDiff, ...]
    ) -> list[str]:
        excluded: list[str] = []
        for diffs in diff_tuples:
            for d in diffs:
                if d.excluded_from_score:
                    excluded.append(f"{d.field_path}: {d.reason}")
        return excluded

    def _collect_major_drifts(
        self,
        facts: tuple[MetricDiff, ...],
        relay: tuple[MetricDiff, ...],
        emotion: tuple[SemanticDiff | MetricDiff, ...],
    ) -> list[str]:
        drifts: list[str] = []
        for d in tuple(facts) + tuple(relay):
            if isinstance(d, MetricDiff) and not d.excluded_from_score and not d.passed:
                if d.absolute_diff is not None and d.tolerance > 0 and d.absolute_diff > d.tolerance * 2:
                    drifts.append(f"{d.field_path}: analyst={d.analyst_value} ai={d.ai_value}")
        for d in emotion:
            if isinstance(d, SemanticDiff) and d.match_type in (MatchType.OPPOSITE,):
                drifts.append(f"{d.field_path}: analyst={d.analyst_label} ai={d.ai_label}")
        return drifts
