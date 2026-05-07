from __future__ import annotations

from decimal import Decimal

from stock_processing_service.domain.services.kline_support_scorer_types import (
    BBLowerStructure,
    GapStructure,
    MAStructure,
    PreviousLowStructure,
    ResolvedSupport,
)


class SupportStructureResolver:
    def __init__(
        self,
        *,
        strict_gap_score: Decimal = Decimal("88"),
        soft_gap_score: Decimal = Decimal("80"),
        prev_low_score: Decimal = Decimal("78"),
        bb_lower_score: Decimal = Decimal("75"),
        ma_score: Decimal = Decimal("70"),
    ) -> None:
        self._strict_gap_score = strict_gap_score
        self._soft_gap_score = soft_gap_score
        self._prev_low_score = prev_low_score
        self._bb_lower_score = bb_lower_score
        self._ma_score = ma_score

    @staticmethod
    def _pick_best_gap(gaps: list[GapStructure]) -> GapStructure | None:
        if not gaps:
            return None
        ranked = sorted(
            gaps,
            key=lambda g: (
                0 if g.strict_hit else 1,
                0 if g.soft_hit else 1,
                g.current_distance_pct,
                -g.resonance_score,
                -g.gap_size_pct,
                g.age_days,
            ),
        )
        return ranked[0]

    def resolve(
        self,
        *,
        gap_structures: list[GapStructure],
        prev_low_structure: PreviousLowStructure | None,
        ma_structures: list[MAStructure],
        bb_lower_structure: BBLowerStructure | None = None,
    ) -> ResolvedSupport:
        best_gap = self._pick_best_gap(gap_structures)

        if best_gap and best_gap.strict_hit and not best_gap.is_filled:
            refs = [
                "primary_support=gap_support",
                "resolver_rule=strict_gap_first",
                f"gap_id={best_gap.gap_id}",
                f"gap_type={best_gap.gap_type}",
                f"gap_lower={best_gap.gap_lower}",
                f"gap_upper={best_gap.gap_upper}",
                f"gap_size_pct={best_gap.gap_size_pct}",
                f"gap_distance_pct={best_gap.current_distance_pct}",
                f"gap_age_days={best_gap.age_days}",
                f"gap_resonance_score={best_gap.resonance_score}",
            ]
            return ResolvedSupport(
                support_type="gap_support",
                support_level=best_gap.gap_lower,
                support_score=self._strict_gap_score,
                support_refs=refs,
                primary_reason="strict_gap_hit",
                gap_hit=True,
                gap_source="gap_structure",
                gap_hit_mode="strict",
                gap_level=best_gap.gap_lower,
                gap_distance_pct=best_gap.current_distance_pct,
            )

        if best_gap and best_gap.soft_hit and best_gap.resonance_score >= Decimal("8"):
            refs = [
                "primary_support=gap_support",
                "resolver_rule=soft_gap_with_resonance",
                f"gap_id={best_gap.gap_id}",
                f"gap_lower={best_gap.gap_lower}",
                f"gap_upper={best_gap.gap_upper}",
                f"gap_distance_pct={best_gap.current_distance_pct}",
                f"gap_resonance_score={best_gap.resonance_score}",
                f"gap_near_ma={best_gap.near_ma}",
                f"gap_near_prev_low={best_gap.near_prev_low}",
            ]
            return ResolvedSupport(
                support_type="gap_support",
                support_level=best_gap.gap_lower,
                support_score=self._soft_gap_score,
                support_refs=refs,
                primary_reason="soft_gap_hit_with_resonance",
                gap_hit=True,
                gap_source="gap_structure",
                gap_hit_mode="soft",
                gap_level=best_gap.gap_lower,
                gap_distance_pct=best_gap.current_distance_pct,
            )

        if bb_lower_structure and bb_lower_structure.is_valid:
            refs = [
                "primary_support=bb_lower_support",
                "resolver_rule=bb_lower_support",
                f"bb_lower_level={bb_lower_structure.level}",
                f"bb_lower_distance_pct={bb_lower_structure.distance_pct}",
            ]
            return ResolvedSupport(
                support_type="bb_lower_support",
                support_level=bb_lower_structure.level,
                support_score=self._bb_lower_score,
                support_refs=refs,
                primary_reason="bb_lower_support",
            )

        if prev_low_structure and prev_low_structure.is_valid:
            refs = [
                "primary_support=prev_low_support",
                "resolver_rule=previous_low_support",
                f"prev_low_level={prev_low_structure.level}",
                f"prev_low_distance_pct={prev_low_structure.distance_pct}",
            ]
            return ResolvedSupport(
                support_type="prev_low_support",
                support_level=prev_low_structure.level,
                support_score=self._prev_low_score,
                support_refs=refs,
                primary_reason="previous_low_support",
            )

        valid_mas = [m for m in ma_structures if m.is_valid]
        if valid_mas:
            valid_mas.sort(key=lambda x: x.distance_pct)
            ma = valid_mas[0]
            refs = [
                "primary_support=ma_support",
                "resolver_rule=ma_support",
                f"ma_type={ma.ma_type}",
                f"ma_level={ma.level}",
                f"ma_distance_pct={ma.distance_pct}",
            ]
            return ResolvedSupport(
                support_type="ma_support",
                support_level=ma.level,
                support_score=self._ma_score,
                support_refs=refs,
                primary_reason="ma_support",
            )

        return ResolvedSupport(
            support_type="none",
            support_level=Decimal("0"),
            support_score=Decimal("0"),
            support_refs=["resolver_rule=no_valid_support"],
            primary_reason="none",
        )
