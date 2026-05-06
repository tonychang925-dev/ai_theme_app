from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from typing import Any


@dataclass(frozen=True)
class CycleDecisionTraceReport:
    trade_date: str
    subject_key: str
    stock_id: str
    scores: dict[str, Any]
    evidence_layers: dict[str, Any]
    final_state: dict[str, Any]
    alive_decision_trace: list[dict[str, Any]]
    consistency: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "subject_key": self.subject_key,
            "stock_id": self.stock_id,
            "scores": self.scores,
            "evidence_layers": self.evidence_layers,
            "final_state": self.final_state,
            "alive_decision_trace": self.alive_decision_trace,
            "consistency": self.consistency,
        }


class CycleDecisionTraceReportBuilder:
    """Explain one Layer B subject judgement without changing state-machine rules."""

    THRESH_MAINLINE_ALIVE = Decimal("60")
    THRESH_MAINLINE_LEADER = Decimal("40")
    THRESH_MAINLINE_EVENT_CONTINUITY = Decimal("40")

    def build(
        self,
        *,
        trade_date: str,
        stock_id: str,
        subject_key: str,
        evidence: dict[str, Any] | None,
        cycle: dict[str, Any] | None,
    ) -> CycleDecisionTraceReport:
        ev = dict(evidence or {})
        cyc = dict(cycle or {})
        evidence_json = self._json_obj(ev.get("evidence_json"))
        leader = evidence_json.get("leader_layer") if isinstance(evidence_json.get("leader_layer"), dict) else {}
        kline = evidence_json.get("kline_layer") if isinstance(evidence_json.get("kline_layer"), dict) else {}
        meta = evidence_json.get("meta") if isinstance(evidence_json.get("meta"), dict) else {}
        persisted_alive = self._bool(cyc.get("final_mainline_alive"))
        recomputed_alive = self._recomputed_alive(ev=ev, cyc=cyc)
        trace = self._alive_trace(ev=ev, cyc=cyc, persisted_alive=persisted_alive)

        return CycleDecisionTraceReport(
            trade_date=trade_date,
            stock_id=stock_id,
            subject_key=subject_key,
            scores={
                "mainline_strength_score": cyc.get("mainline_strength_score"),
                "leader_alive_score": ev.get("leader_alive_score"),
                "event_strength_score": ev.get("event_strength_score"),
                "event_continuity_score": ev.get("event_continuity_score"),
                "red_ratio": ev.get("red_ratio"),
                "big_drop_ratio": ev.get("big_drop_ratio"),
                "theme_support_score": ev.get("theme_support_score"),
                "break_start_pivot": ev.get("break_start_pivot"),
                "divergence_score": cyc.get("divergence_score"),
                "repair_score": cyc.get("repair_score"),
                "fade_watch_score": cyc.get("fade_watch_score"),
                "fade_confirmed_score": cyc.get("fade_confirmed_score"),
            },
            evidence_layers={
                "event": {
                    "event_count_3d": ev.get("event_count_3d"),
                    "event_count_7d": ev.get("event_count_7d"),
                    "strong_event_count_7d": ev.get("strong_event_count_7d"),
                    "event_recency_days": ev.get("event_recency_days"),
                },
                "leader": {
                    "leader_score_source": leader.get("leader_score_source"),
                    "leader_stock_id": leader.get("leader_stock_id"),
                    "leader_pct_chg": leader.get("leader_pct_chg"),
                    "leader_limit_up": leader.get("leader_limit_up"),
                    "leader_breakdown_flag": ev.get("leader_breakdown_flag"),
                    "front_row_survival_ratio": ev.get("front_row_survival_ratio"),
                    "front_row_limit_up_count": leader.get("front_row_limit_up_count"),
                },
                "board": {
                    "limit_up_count": ev.get("limit_up_count"),
                    "limit_down_count": ev.get("limit_down_count"),
                    "red_ratio": ev.get("red_ratio"),
                    "big_drop_ratio": ev.get("big_drop_ratio"),
                    "front_row_strength_score": ev.get("front_row_strength_score"),
                },
                "kline": {
                    "theme_support_score": ev.get("theme_support_score"),
                    "break_start_pivot": ev.get("break_start_pivot"),
                    "above_ma10": kline.get("above_ma10", ev.get("above_ma10")),
                    "above_ma20": kline.get("above_ma20", ev.get("above_ma20")),
                    "kline_quality": kline.get("kline_quality"),
                    "theme_ret_3d": kline.get("theme_ret_3d"),
                    "theme_ret_5d": kline.get("theme_ret_5d"),
                    "theme_ret_10d": kline.get("theme_ret_10d"),
                },
            },
            final_state={
                "final_cycle_state": cyc.get("final_cycle_state"),
                "final_mainline_alive": persisted_alive,
                "recomputed_alive_from_current_policy": recomputed_alive,
                "decision_path": cyc.get("decision_path") or cyc.get("state_transition_reason"),
                "rule_reasons": cyc.get("rule_reasons"),
                "risk_flags": cyc.get("risk_flags"),
            },
            alive_decision_trace=trace,
            consistency={
                "evidence_snapshot_version": ev.get("snapshot_version") or meta.get("snapshot_version"),
                "evidence_batch_id": ev.get("batch_id") or meta.get("batch_id"),
                "evidence_trace_id": ev.get("trace_id") or meta.get("trace_id"),
                "evidence_source_version": ev.get("source_version"),
                "evidence_created_at": ev.get("created_at"),
                "cycle_snapshot_version": cyc.get("snapshot_version"),
                "cycle_source_version": cyc.get("source_version"),
                "cycle_state_machine_version": cyc.get("state_machine_version"),
                "cycle_created_at": cyc.get("created_at"),
                "version_alignment_status": self._version_alignment_status(ev=ev, meta=meta, cyc=cyc),
                "persisted_vs_recomputed_alive": {
                    "persisted": persisted_alive,
                    "recomputed": recomputed_alive,
                    "mismatch": persisted_alive != recomputed_alive,
                },
            },
        )

    def _alive_trace(
        self,
        *,
        ev: dict[str, Any],
        cyc: dict[str, Any],
        persisted_alive: bool,
    ) -> list[dict[str, Any]]:
        mainline_strength = self._dec(cyc.get("mainline_strength_score"))
        leader_alive = self._dec(ev.get("leader_alive_score"))
        event_continuity = self._dec(ev.get("event_continuity_score"))
        strong_event_count = int(ev.get("strong_event_count_7d") or 0)
        final_state = str(cyc.get("final_cycle_state") or "")
        support_break = bool(ev.get("break_start_pivot")) or self._dec(ev.get("theme_support_score")) <= Decimal("35")
        fade_confirmed = str(cyc.get("final_cycle_state") or "") == "fade_confirmed"
        recomputed_alive = self._recomputed_alive(ev=ev, cyc=cyc)
        return [
            self._rule("mainline_strength", mainline_strength >= self.THRESH_MAINLINE_ALIVE, mainline_strength, self.THRESH_MAINLINE_ALIVE),
            self._rule("leader_alive", leader_alive >= self.THRESH_MAINLINE_LEADER, leader_alive, self.THRESH_MAINLINE_LEADER),
            {
                "rule": "event_continuity_or_strong_event",
                "passed": strong_event_count > 0 or event_continuity >= self.THRESH_MAINLINE_EVENT_CONTINUITY,
                "actual": {
                    "strong_event_count_7d": strong_event_count,
                    "event_continuity_score": str(event_continuity),
                },
                "threshold": "strong_event_count_7d>0 OR event_continuity_score>=40",
            },
            {
                "rule": "mainline_alive_rule",
                "passed": (
                    mainline_strength >= self.THRESH_MAINLINE_ALIVE
                    and leader_alive >= self.THRESH_MAINLINE_LEADER
                    and (strong_event_count > 0 or event_continuity >= self.THRESH_MAINLINE_EVENT_CONTINUITY)
                    and not fade_confirmed
                ),
                "reason": "diagnostic score flag only; does not directly decide final_mainline_alive",
            },
            {
                "rule": "support_break_for_fade_confirmed",
                "passed": support_break,
                "actual": {
                    "break_start_pivot": bool(ev.get("break_start_pivot")),
                    "theme_support_score": str(self._dec(ev.get("theme_support_score"))),
                },
                "threshold": "break_start_pivot=true OR theme_support_score<=35",
            },
            {
                "rule": "final_state_policy",
                "passed": final_state != "fade_confirmed",
                "actual": final_state,
                "threshold": "final_cycle_state != fade_confirmed",
                "reason": "old-chain-compatible final_mainline_alive is not fade_confirmed",
            },
            {
                "rule": "persisted_alive_matches_current_policy",
                "passed": persisted_alive == recomputed_alive,
                "actual": persisted_alive,
                "expected": recomputed_alive,
                "reason": (
                    "persisted final_mainline_alive differs from recomputed current-policy result"
                    if persisted_alive != recomputed_alive
                    else "persisted final_mainline_alive matches current-policy result"
                ),
            },
        ]

    def _recomputed_alive(self, *, ev: dict[str, Any], cyc: dict[str, Any]) -> bool:
        return str(cyc.get("final_cycle_state") or "") != "fade_confirmed"

    @staticmethod
    def _rule(rule: str, passed: bool, actual: Decimal, threshold: Decimal) -> dict[str, Any]:
        return {
            "rule": rule,
            "passed": bool(passed),
            "actual": str(actual),
            "threshold": str(threshold),
        }

    @staticmethod
    def _version_alignment_status(*, ev: dict[str, Any], meta: dict[str, Any], cyc: dict[str, Any]) -> str:
        evidence_snapshot = ev.get("snapshot_version") or meta.get("snapshot_version")
        cycle_snapshot = cyc.get("snapshot_version")
        if evidence_snapshot and not cycle_snapshot:
            return "cycle_snapshot_version_missing"
        if evidence_snapshot and cycle_snapshot and str(evidence_snapshot) != str(cycle_snapshot):
            return "snapshot_version_mismatch"
        return "unknown" if not evidence_snapshot and not cycle_snapshot else "aligned"

    @staticmethod
    def _json_obj(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return dict(parsed) if isinstance(parsed, dict) else {}
        return {}

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

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "y"}
        return bool(value)
