from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from stock_processing_service.domain.services.strong_watch_contracts import ADMISSION_REQUIRED_FIELDS


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
    pass_reasons: list[str]
    admission_status: str


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
        recent_limit_up_count: int,
        subject_limit_up_count: int,
        subject_strong_count: int,
        final_mainline_alive: bool,
        board_effect_confirmed: bool,
        two_board_entry: bool,
        pct_chg: Decimal,
        support_type: str,
        support_score: Decimal,
        is_leader: bool,
        rank_order: int,
    ) -> StrongWatchAdmissionDecision:
        # Rule A: 涨停基因（旧链兼容：两连板旁路也视作基因成立）
        limitup_gene_pass = prior7_limitup_days >= 1 or recent_limit_up_count >= 2 or two_board_entry

        # Rule B: 题材合力（主线存活 + 板块合力）
        # 不再使用“缺统计默认通过”放宽，避免 Layer C 过量纳入。
        # 两连板旁路由 two_board_entry 处理，而非把所有主线 alive 一律放行。
        theme_synergy_pass = final_mainline_alive and (
            board_effect_confirmed or subject_limit_up_count >= 2 or subject_strong_count >= 3
        )

        # Rule C: 量价健康（避免极端日）
        volume_price_health_pass = Decimal("-6") <= pct_chg <= Decimal("6")

        # Rule D: 结构健康（旧链口径优先：gap/前低/平台）
        structure_health_pass = support_type in {
            "gap_support",
            "previous_low",
            "prev_low_support",
            "platform_support",
        } and support_score >= Decimal("55")
        if support_type == "ma_support" and support_score >= Decimal("70"):
            structure_health_pass = True

        pass_count_4of3 = int(limitup_gene_pass) + int(theme_synergy_pass) + int(volume_price_health_pass) + int(
            structure_health_pass
        )

        # Hard rejects
        reject_no_limitup_gene = not limitup_gene_pass
        # 两连板旁路时不因“非主线协同”直接拒绝
        reject_isolated_theme = (not theme_synergy_pass) and (not two_board_entry) and (not final_mainline_alive)
        reject_break_support_with_heavy_drop = (not structure_health_pass) and pct_chg <= Decimal("-6")
        pass_reasons: list[str] = []
        if limitup_gene_pass:
            pass_reasons.append("limitup_gene_pass")
        if theme_synergy_pass:
            pass_reasons.append("theme_synergy_pass")
        if volume_price_health_pass:
            pass_reasons.append("volume_price_health_pass")
        if structure_health_pass:
            pass_reasons.append("structure_health_pass")

        # Gate: LAYER_C_ALLOW_OLD_CHAIN_HARD_PASS (Phase 1: default 1, Phase 2: default 0)
        if os.environ.get("LAYER_C_ALLOW_OLD_CHAIN_HARD_PASS", "1") == "1":
            old_chain_hard_pass = bool(
                limitup_gene_pass
                and (
                    pass_count_4of3 >= 3
                    or (theme_synergy_pass and recent_limit_up_count >= 2)
                    or (two_board_entry and pass_count_4of3 >= 2)
                    or ((is_leader or rank_order <= 3) and support_score >= Decimal("60"))
                    or (final_mainline_alive and limitup_gene_pass and support_score >= Decimal("60"))
                )
            )
        else:
            # Strict document path: pure 4-of-3 admission
            old_chain_hard_pass = False

        if old_chain_hard_pass:
            admission_status = "formal"
        elif pass_count_4of3 >= 3:
            admission_status = "formal"
        elif limitup_gene_pass and structure_health_pass and volume_price_health_pass:
            admission_status = "observe_only"
        else:
            admission_status = "reject"

        return StrongWatchAdmissionDecision(
            limitup_gene_pass=limitup_gene_pass,
            theme_synergy_pass=theme_synergy_pass,
            volume_price_health_pass=volume_price_health_pass,
            structure_health_pass=structure_health_pass,
            pass_count_4of3=pass_count_4of3,
            reject_no_limitup_gene=reject_no_limitup_gene,
            reject_isolated_theme=reject_isolated_theme,
            reject_break_support_with_heavy_drop=reject_break_support_with_heavy_drop,
            pass_reasons=pass_reasons,
            admission_status=admission_status,
        )
    @staticmethod
    def required_fields() -> tuple[str, ...]:
        return ADMISSION_REQUIRED_FIELDS
