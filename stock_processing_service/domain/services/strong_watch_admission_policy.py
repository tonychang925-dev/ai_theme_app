from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class StrongWatchAdmissionDecision:
    limitup_gene_pass: bool
    theme_synergy_pass: bool
    volume_price_health_pass: bool
    structure_health_pass: bool
    pass_count_4of3: int
    reject_no_limitup_gene: bool
    reject_isolated_theme: bool
    reject_break_support_with_heavy_drop: bool
    reject_junk_follower: bool
    hard_reject_any: bool
    pass_reasons: list[str]


class StrongWatchAdmissionPolicy:
    """
    Layer C-2 admission policy.

    This is the explicit 4-of-3 + hard-reject decision block so Layer C is
    an object pool gate, not only a score ranker.
    """

    @staticmethod
    def _d(value: Any, default: str = "0") -> Decimal:
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    def assess(
        self,
        *,
        prior7_limitup_days: int,
        subject_limit_up_count: int,
        subject_strong_count: int,
        pct_chg: Decimal,
        support_type: str,
        support_score: Decimal,
        is_leader: bool,
        rank_order: int,
    ) -> StrongWatchAdmissionDecision:
        # Rule A: 涨停基因
        limitup_gene_pass = prior7_limitup_days >= 1

        # Rule B: 题材合力（主线+板块合力可在上游 universe gate 保证）
        theme_synergy_pass = subject_limit_up_count >= 2 or subject_strong_count >= 3

        # Rule C: 量价健康（审计口径，偏保守）
        volume_price_health_pass = pct_chg >= Decimal("-5")

        # Rule D: 结构健康
        structure_health_pass = support_type in {
            "gap_support",
            "previous_low",
            "prev_low_support",
            "platform_support",
            "ma_support",
        } and support_score >= Decimal("55")

        pass_count_4of3 = int(limitup_gene_pass) + int(theme_synergy_pass) + int(volume_price_health_pass) + int(
            structure_health_pass
        )

        # Hard rejects
        reject_no_limitup_gene = not limitup_gene_pass
        reject_isolated_theme = not theme_synergy_pass
        reject_break_support_with_heavy_drop = (not structure_health_pass) and pct_chg <= Decimal("-6")
        reject_junk_follower = (not is_leader) and rank_order > 10 and (not limitup_gene_pass) and (
            not theme_synergy_pass
        )
        hard_reject_any = (
            reject_no_limitup_gene
            or reject_isolated_theme
            or reject_break_support_with_heavy_drop
            or reject_junk_follower
        )

        pass_reasons: list[str] = []
        if limitup_gene_pass:
            pass_reasons.append("limitup_gene_pass")
        if theme_synergy_pass:
            pass_reasons.append("theme_synergy_pass")
        if volume_price_health_pass:
            pass_reasons.append("volume_price_health_pass")
        if structure_health_pass:
            pass_reasons.append("structure_health_pass")

        return StrongWatchAdmissionDecision(
            limitup_gene_pass=limitup_gene_pass,
            theme_synergy_pass=theme_synergy_pass,
            volume_price_health_pass=volume_price_health_pass,
            structure_health_pass=structure_health_pass,
            pass_count_4of3=pass_count_4of3,
            reject_no_limitup_gene=reject_no_limitup_gene,
            reject_isolated_theme=reject_isolated_theme,
            reject_break_support_with_heavy_drop=reject_break_support_with_heavy_drop,
            reject_junk_follower=reject_junk_follower,
            hard_reject_any=hard_reject_any,
            pass_reasons=pass_reasons,
        )

