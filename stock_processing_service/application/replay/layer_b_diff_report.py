from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class LayerBDiffReport:
    trade_date: str
    stock_id: str
    report_type: str
    summary: dict[str, Any]
    subject_rows: list[dict[str, Any]]
    field_names: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "stock_id": self.stock_id,
            "report_type": self.report_type,
            "summary": self.summary,
            "field_names": self.field_names,
            "subject_rows": self.subject_rows,
        }


class LayerBDiffReportBuilder:
    """Build a Layer B subject cross-diff report for one target stock."""

    FIELD_NAMES = [
        "subject_key",
        "theme_name",
        "category",
        "leader_alive_score",
        "leader_score_source",
        "leader_breakdown_flag",
        "front_row_survival_ratio",
        "front_row_limit_up_count",
        "event_strength_score",
        "event_continuity_score",
        "event_count_3d",
        "event_count_7d",
        "strong_event_count_7d",
        "event_recency_days",
        "limit_up_count",
        "red_ratio",
        "big_drop_ratio",
        "front_row_strength_score",
        "theme_support_score",
        "break_start_pivot",
        "above_ma10",
        "above_ma20",
        "kline_quality",
        "theme_ret_3d",
        "theme_ret_5d",
        "theme_ret_10d",
        "mainline_strength_score",
        "fade_watch_score",
        "fade_confirmed_score",
        "divergence_score",
        "repair_score",
        "final_cycle_state",
        "final_mainline_alive",
        "alive_decision_reason",
    ]

    def build(
        self,
        *,
        trade_date: str,
        stock_id: str,
        evidence_rows: list[dict[str, Any]],
        cycle_rows: list[dict[str, Any]],
    ) -> LayerBDiffReport:
        cycle_by_subject = {str(row.get("subject_key") or ""): dict(row) for row in cycle_rows}
        subject_rows: list[dict[str, Any]] = []
        for raw in evidence_rows:
            evidence = dict(raw)
            subject_key = str(evidence.get("subject_key") or "")
            cycle = cycle_by_subject.get(subject_key, {})
            subject_rows.append(self._subject_row(evidence=evidence, cycle=cycle))

        subject_rows.sort(
            key=lambda row: (
                {"A": 0, "B": 1, "C": 2}.get(str(row.get("category") or ""), 9),
                -self._dec(row.get("mainline_strength_score")),
                str(row.get("subject_key") or ""),
            )
        )
        summary = self._summary(subject_rows)
        return LayerBDiffReport(
            trade_date=trade_date,
            stock_id=stock_id,
            report_type="new_chain_self_diff",
            summary=summary,
            subject_rows=subject_rows,
            field_names=list(self.FIELD_NAMES),
        )

    def _subject_row(self, *, evidence: dict[str, Any], cycle: dict[str, Any]) -> dict[str, Any]:
        evidence_json = evidence.get("evidence_json") if isinstance(evidence.get("evidence_json"), dict) else {}
        leader = evidence_json.get("leader_layer") if isinstance(evidence_json.get("leader_layer"), dict) else {}
        kline = evidence_json.get("kline_layer") if isinstance(evidence_json.get("kline_layer"), dict) else {}
        row = {
            "subject_key": evidence.get("subject_key"),
            "theme_name": evidence.get("theme_name"),
            "leader_alive_score": evidence.get("leader_alive_score"),
            "leader_score_source": leader.get("leader_score_source"),
            "leader_breakdown_flag": evidence.get("leader_breakdown_flag"),
            "front_row_survival_ratio": evidence.get("front_row_survival_ratio"),
            "front_row_limit_up_count": leader.get("front_row_limit_up_count"),
            "event_strength_score": evidence.get("event_strength_score"),
            "event_continuity_score": evidence.get("event_continuity_score"),
            "event_count_3d": evidence.get("event_count_3d"),
            "event_count_7d": evidence.get("event_count_7d"),
            "strong_event_count_7d": evidence.get("strong_event_count_7d"),
            "event_recency_days": evidence.get("event_recency_days"),
            "limit_up_count": evidence.get("limit_up_count"),
            "red_ratio": evidence.get("red_ratio"),
            "big_drop_ratio": evidence.get("big_drop_ratio"),
            "front_row_strength_score": evidence.get("front_row_strength_score"),
            "theme_support_score": evidence.get("theme_support_score"),
            "break_start_pivot": evidence.get("break_start_pivot"),
            "above_ma10": kline.get("above_ma10", evidence.get("above_ma10")),
            "above_ma20": kline.get("above_ma20", evidence.get("above_ma20")),
            "kline_quality": kline.get("kline_quality"),
            "theme_ret_3d": kline.get("theme_ret_3d"),
            "theme_ret_5d": kline.get("theme_ret_5d"),
            "theme_ret_10d": kline.get("theme_ret_10d"),
            "mainline_strength_score": cycle.get("mainline_strength_score"),
            "fade_watch_score": cycle.get("fade_watch_score"),
            "fade_confirmed_score": cycle.get("fade_confirmed_score"),
            "divergence_score": cycle.get("divergence_score"),
            "repair_score": cycle.get("repair_score"),
            "final_cycle_state": cycle.get("final_cycle_state"),
            "final_mainline_alive": cycle.get("final_mainline_alive"),
            "alive_decision_reason": self._alive_reason(evidence=evidence, cycle=cycle),
        }
        row["category"] = self._category(row)
        row["diagnostic_hints"] = self._diagnostic_hints(row)
        return row

    @classmethod
    def _category(cls, row: dict[str, Any]) -> str:
        leader_alive = cls._dec(row.get("leader_alive_score")) >= Decimal("40")
        alive = bool(row.get("final_mainline_alive"))
        if leader_alive and alive:
            return "A"
        if leader_alive and not alive:
            return "B"
        return "C"

    @classmethod
    def _diagnostic_hints(cls, row: dict[str, Any]) -> list[str]:
        hints: list[str] = []
        if cls._dec(row.get("event_continuity_score")) < Decimal("40") and int(row.get("strong_event_count_7d") or 0) <= 0:
            hints.append("event_layer_below_alive_gate")
        if cls._dec(row.get("mainline_strength_score")) < Decimal("60"):
            hints.append("mainline_strength_below_60")
        if cls._dec(row.get("theme_support_score")) <= Decimal("35") or bool(row.get("break_start_pivot")):
            hints.append("kline_support_weak")
        if cls._dec(row.get("red_ratio")) <= Decimal("0.45") or cls._dec(row.get("big_drop_ratio")) >= Decimal("0.30"):
            hints.append("board_structure_weak")
        if str(row.get("final_cycle_state") or "") == "divergence":
            hints.append("state_machine_selected_divergence")
        return hints

    @classmethod
    def _alive_reason(cls, *, evidence: dict[str, Any], cycle: dict[str, Any]) -> str:
        if bool(cycle.get("final_mainline_alive")):
            return "alive_conditions_passed"
        failed: list[str] = []
        mainline_strength = cls._dec(cycle.get("mainline_strength_score"))
        leader_alive = cls._dec(evidence.get("leader_alive_score"))
        if mainline_strength < Decimal("60"):
            failed.append(f"mainline_strength_score={mainline_strength} below threshold=60")
        if leader_alive < Decimal("40"):
            failed.append(f"leader_alive_score={leader_alive} below threshold=40")
        continuity_ok = int(evidence.get("strong_event_count_7d") or 0) > 0 or cls._dec(
            evidence.get("event_continuity_score")
        ) >= Decimal("40")
        if not continuity_ok:
            failed.append("strong_event_count_7d=0 and event_continuity_score below threshold=40")
        if failed:
            return "; ".join(failed)
        return f"state={cycle.get('final_cycle_state')} with alive flag false from persisted judgement"

    @classmethod
    def _summary(cls, subject_rows: list[dict[str, Any]]) -> dict[str, Any]:
        by_category = {"A": 0, "B": 0, "C": 0}
        hint_counts: dict[str, int] = {}
        for row in subject_rows:
            category = str(row.get("category") or "")
            if category in by_category:
                by_category[category] += 1
            for hint in row.get("diagnostic_hints") or []:
                hint_counts[str(hint)] = hint_counts.get(str(hint), 0) + 1
        return {
            "subject_count": len(subject_rows),
            "category_counts": by_category,
            "hint_counts": dict(sorted(hint_counts.items())),
            "best_alive_subject": cls._best_subject(subject_rows, alive=True),
            "best_dead_subject": cls._best_subject(subject_rows, alive=False),
        }

    @classmethod
    def _best_subject(cls, subject_rows: list[dict[str, Any]], *, alive: bool) -> dict[str, Any] | None:
        candidates = [row for row in subject_rows if bool(row.get("final_mainline_alive")) is alive]
        if not candidates:
            return None
        row = max(candidates, key=lambda item: cls._dec(item.get("mainline_strength_score")))
        return {
            "subject_key": row.get("subject_key"),
            "theme_name": row.get("theme_name"),
            "mainline_strength_score": row.get("mainline_strength_score"),
            "final_cycle_state": row.get("final_cycle_state"),
            "final_mainline_alive": row.get("final_mainline_alive"),
        }

    @staticmethod
    def _dec(value: Any) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0")
