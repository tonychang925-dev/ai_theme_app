from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stock_processing_service.application.replay.layer_b_transition_explain import LayerBTransitionExplainBuilder


@dataclass(frozen=True)
class LayerBDiagnosticReport:
    trade_date: str
    subject_key: str
    stock_id: str
    layer_b: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "subject_key": self.subject_key,
            "stock_id": self.stock_id,
            "layer_b": self.layer_b,
        }


class LayerBDiagnosticReportBuilder:
    def build(
        self,
        *,
        trade_date: str,
        stock_id: str,
        subject_key: str,
        evidence: dict[str, Any] | None,
        cycle: dict[str, Any] | None,
    ) -> LayerBDiagnosticReport:
        ev = dict(evidence or {})
        cyc = dict(cycle or {})
        evidence_json = ev.get("evidence_json") if isinstance(ev.get("evidence_json"), dict) else {}
        kline = evidence_json.get("kline_layer") if isinstance(evidence_json.get("kline_layer"), dict) else {}
        transition_explain = LayerBTransitionExplainBuilder().build(
            trade_date=trade_date,
            subject_key=subject_key,
            evidence=ev,
            cycle=cyc,
        )
        return LayerBDiagnosticReport(
            trade_date=trade_date,
            stock_id=stock_id,
            subject_key=subject_key,
            layer_b={
                "evidence": {
                    "theme_name": ev.get("theme_name"),
                    "event_strength_score": ev.get("event_strength_score"),
                    "event_continuity_score": ev.get("event_continuity_score"),
                    "strong_event_count_7d": ev.get("strong_event_count_7d"),
                    "event_recency_days": ev.get("event_recency_days"),
                    "leader_alive_score": ev.get("leader_alive_score"),
                    "leader_breakdown_flag": ev.get("leader_breakdown_flag"),
                    "relay_strength_score": ev.get("relay_strength_score"),
                    "front_row_survival_ratio": ev.get("front_row_survival_ratio"),
                    "limit_up_count": ev.get("limit_up_count"),
                    "limit_down_count": ev.get("limit_down_count"),
                    "red_ratio": ev.get("red_ratio"),
                    "big_drop_ratio": ev.get("big_drop_ratio"),
                    "front_row_strength_score": ev.get("front_row_strength_score"),
                    "theme_support_score": ev.get("theme_support_score"),
                    "break_start_pivot": ev.get("break_start_pivot"),
                    "above_ma5": kline.get("above_ma5"),
                    "above_ma10": kline.get("above_ma10", ev.get("above_ma10")),
                    "above_ma20": kline.get("above_ma20", ev.get("above_ma20")),
                    "theme_ret_3d": kline.get("theme_ret_3d"),
                    "theme_ret_5d": kline.get("theme_ret_5d"),
                    "theme_ret_10d": kline.get("theme_ret_10d"),
                    "kline_quality": kline.get("kline_quality"),
                },
                "cycle": {
                    "mainline_strength_score": cyc.get("mainline_strength_score"),
                    "fade_watch_score": cyc.get("fade_watch_score"),
                    "fade_confirmed_score": cyc.get("fade_confirmed_score"),
                    "divergence_score": cyc.get("divergence_score"),
                    "repair_score": cyc.get("repair_score"),
                    "final_cycle_state": cyc.get("final_cycle_state"),
                    "final_mainline_alive": cyc.get("final_mainline_alive"),
                    "alive_decision_reason": transition_explain.alive_decision_reason,
                },
                "transition_explain": transition_explain.to_dict(),
                "diff_fields": self._diagnostic_fields(ev=ev, cyc=cyc, kline=kline),
            },
        )

    @staticmethod
    def _diagnostic_fields(
        *,
        ev: dict[str, Any],
        cyc: dict[str, Any],
        kline: dict[str, Any],
    ) -> list[dict[str, Any]]:
        fields = {
            "event_strength_score": ev.get("event_strength_score"),
            "event_continuity_score": ev.get("event_continuity_score"),
            "strong_event_count_7d": ev.get("strong_event_count_7d"),
            "event_recency_days": ev.get("event_recency_days"),
            "leader_alive_score": ev.get("leader_alive_score"),
            "leader_breakdown_flag": ev.get("leader_breakdown_flag"),
            "relay_strength_score": ev.get("relay_strength_score"),
            "front_row_survival_ratio": ev.get("front_row_survival_ratio"),
            "limit_up_count": ev.get("limit_up_count"),
            "limit_down_count": ev.get("limit_down_count"),
            "red_ratio": ev.get("red_ratio"),
            "big_drop_ratio": ev.get("big_drop_ratio"),
            "front_row_strength_score": ev.get("front_row_strength_score"),
            "theme_support_score": ev.get("theme_support_score"),
            "break_start_pivot": ev.get("break_start_pivot"),
            "above_ma5": kline.get("above_ma5"),
            "above_ma10": kline.get("above_ma10", ev.get("above_ma10")),
            "above_ma20": kline.get("above_ma20", ev.get("above_ma20")),
            "theme_ret_3d": kline.get("theme_ret_3d"),
            "theme_ret_5d": kline.get("theme_ret_5d"),
            "theme_ret_10d": kline.get("theme_ret_10d"),
            "kline_quality": kline.get("kline_quality"),
            "mainline_strength_score": cyc.get("mainline_strength_score"),
            "fade_watch_score": cyc.get("fade_watch_score"),
            "fade_confirmed_score": cyc.get("fade_confirmed_score"),
            "divergence_score": cyc.get("divergence_score"),
            "repair_score": cyc.get("repair_score"),
            "final_cycle_state": cyc.get("final_cycle_state"),
            "final_mainline_alive": cyc.get("final_mainline_alive"),
        }
        return [
            {
                "field": name,
                "new_value": value,
                "old_value": None,
                "diff_status": "diagnostic_only",
            }
            for name, value in fields.items()
        ]
