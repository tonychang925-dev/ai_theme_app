from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidence


@dataclass(frozen=True)
class CycleJudgement:
    stock_id: str
    subject_key: str
    subject_name: str
    mainline_strength_score: Decimal
    fade_watch_score: Decimal
    fade_confirmed_score: Decimal
    divergence_score: Decimal
    repair_score: Decimal
    acceleration_score: Decimal
    fermentation_score: Decimal
    fade_confirmed_evidence_count: int
    final_cycle_state: str
    final_mainline_alive: bool
    decision_path: str = ""
    evidence_count: int = 0
    fade_reason_codes: list[str] | None = None
    mainline_alive_rule: bool = False
    support_break: bool = False
    score_flags: dict[str, bool] | None = None


class CycleJudgementService:
    def judge_many(self, evidences: list[CycleEvidence]) -> list[CycleJudgement]:
        return [self.judge_one(e) for e in evidences]

    def judge_one(self, e: CycleEvidence) -> CycleJudgement:
        # ── 1:1 复刻旧链 theme_cycle_judgement_service_v2.py 评分公式 ──

        # 1) mainline_strength_score（公式一致，仅字段名不同）
        mainline_strength = (
            e.event_score * Decimal("0.22")       # 旧链: event_strength_score
            + e.continuity_score * Decimal("0.12") # 旧链: event_continuity_score
            + e.leader_score * Decimal("0.26")     # 旧链: leader_alive_score
            + e.relay_score * Decimal("0.16")      # 旧链: relay_strength_score
            + e.board_score * Decimal("0.14")      # 旧链: front_row_strength_score
            + e.support_score * Decimal("0.10")    # 旧链: theme_support_score
        )

        # 旧链 red_ratio：实际板块红盘比（现在从 evidence 取真实值，不再合成）
        red_ratio = max(Decimal("0"), min(Decimal("1"), e.red_ratio))

        # 2) fade_watch_score — 旧链公式：
        # leader_break * 0.35 + (1-red_ratio) * 45 + big_drop_ratio * 35 + min(limit_down * 10, 20)
        leader_break = Decimal("100") if e.leader_breakdown_flag else Decimal("0")
        fade_watch = (
            leader_break * Decimal("0.35")
            + (Decimal("1") - red_ratio) * Decimal("45")
            + e.big_drop_ratio * Decimal("35")
            + min(Decimal(str(e.limit_down_count)) * Decimal("10"), Decimal("20"))
        )

        # 3) fade_confirmed_score — 旧链公式：
        # leader_break * 0.45 + min(limit_down * 14, 35) + (1-red_ratio) * 28 + max(0, 40 - relay) * 0.45
        fade_confirmed = (
            leader_break * Decimal("0.45")
            + min(Decimal(str(e.limit_down_count)) * Decimal("14"), Decimal("35"))
            + (Decimal("1") - red_ratio) * Decimal("28")
            + max(Decimal("0"), Decimal("40") - e.relay_score) * Decimal("0.45")
        )

        # 4) divergence_score — 旧链公式：
        # leader * 0.30 + relay * 0.25 + front_row_survival * 20 + support * 0.20 + (1-red_ratio) * 15
        divergence = (
            e.leader_score * Decimal("0.30")
            + e.relay_score * Decimal("0.25")
            + e.front_row_survival_ratio * Decimal("20")
            + e.support_score * Decimal("0.20")
            + (Decimal("1") - red_ratio) * Decimal("15")
        )

        # 5) repair_score — 旧链公式（一致）
        repair = (
            e.continuity_score * Decimal("0.22")
            + e.relay_score * Decimal("0.24")
            + e.support_score * Decimal("0.20")
            + red_ratio * Decimal("18")
            + e.leader_score * Decimal("0.16")
        )

        # acceleration / fermentation: 旧链用 mainline_strength 阈值判定，非独立公式
        acceleration = mainline_strength  # 旧链: mainline_strength >= 75 → acceleration
        fermentation = mainline_strength  # 旧链: mainline_strength >= 60 → fermentation

        # ── 6 维 fade_confirmed 证据计数（等价旧链 _count_fade_confirmed_evidence）──
        evidence_count = 0
        if e.leader_breakdown_flag:
            evidence_count += 1
        if e.limit_down_count >= 1:
            evidence_count += 1
        if red_ratio <= Decimal("0.45"):
            evidence_count += 1
        if e.big_drop_ratio >= Decimal("0.30"):
            evidence_count += 1
        if e.relay_score <= Decimal("35"):
            evidence_count += 1
        if e.support_score <= Decimal("35"):  # 旧链: theme_support_score <= 35
            evidence_count += 1

        # ── support_break：旧链硬退潮必须满足 K 线破位 ──
        support_break = bool(
            e.break_start_pivot or e.theme_support_score <= Decimal("35")
        )

        # ── Fixed priority（与旧链一致）──
        # 1 fade_confirmed (score>=60, evidence>=3, support_break)
        # 2 repair (from divergence/fade_watch), 3 divergence, 4 fade_watch,
        # 5 acceleration, 6 fermentation, 7 start
        THRESHOLDS = {
            "fade_confirmed_min": Decimal("60"),
            "fade_watch_min": Decimal("50"),
            "repair_min": Decimal("65"),
            "divergence_min": Decimal("60"),
            "acceleration_min": Decimal("75"),
            "fermentation_min": Decimal("60"),
        }

        if fade_confirmed >= THRESHOLDS["fade_confirmed_min"] and evidence_count >= 3 and support_break:
            state = "fade_confirmed"
        elif repair >= THRESHOLDS["repair_min"] and e.previous_state in {"divergence", "fade_watch"}:
            state = "repair"
        elif divergence >= THRESHOLDS["divergence_min"]:
            state = "divergence"
        elif fade_watch >= THRESHOLDS["fade_watch_min"]:
            state = "fade_watch"
        elif acceleration >= THRESHOLDS["acceleration_min"]:
            state = "acceleration"
        elif fermentation >= THRESHOLDS["fermentation_min"]:
            state = "fermentation"
        else:
            state = "start"

        # ── mainline_alive_rule（旧链口径）──
        mainline_alive = (
            mainline_strength >= Decimal("60")
            and e.leader_score >= Decimal("40")
            and (e.strong_event_count_7d > 0 or e.continuity_score >= Decimal("40"))
            and state != "fade_confirmed"
        )

        return CycleJudgement(
            stock_id=e.stock_id,
            subject_key=e.subject_key,
            subject_name=e.subject_name,
            mainline_strength_score=mainline_strength,
            fade_watch_score=fade_watch,
            fade_confirmed_score=fade_confirmed,
            divergence_score=divergence,
            repair_score=repair,
            acceleration_score=acceleration,
            fermentation_score=fermentation,
            fade_confirmed_evidence_count=evidence_count,
            final_cycle_state=state,
            final_mainline_alive=not (state == "fade_confirmed"),  # 旧链口径: final_mainline_alive = not fade_confirmed
            support_break=support_break,
            mainline_alive_rule=bool(mainline_alive),
        )
