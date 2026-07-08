"""M2.5 — Metrics Validation Snapshot (Phase 0.5).

Purpose: Freeze daily MarketMetricsSnapshot as immutable facts, then
compare against analyst PDF reference numbers to detect drift.

Every time the calculator is changed, validation snapshots serve as
regression safety — no more "33 vs 44" surprises.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from .contracts import MarketMetricsSnapshot


# ── Validation types ──

@dataclass(frozen=True, slots=True)
class MetricDiff:
    metric_name: str               # e.g. "limit_up.total_count"
    system_value: float | int | None
    analyst_value: float | int | None
    absolute_diff: float | None
    relative_diff_pct: float | None  # e.g. 2.4 = 2.4% off
    status: str                    # "match" | "within_tolerance" | "diverged" | "missing_analyst" | "missing_system"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    trade_date: date
    generated_at: datetime
    snapshot_version: str           # "1.1"
    snapshot_frozen: bool           # True = immutable

    diffs: tuple[MetricDiff, ...]
    match_count: int
    diverged_count: int
    missing_analyst_count: int     # system has metric, analyst doesn't
    missing_system_count: int      # analyst has metric, system doesn't

    overall_status: str            # "ok" | "tolerable" | "review_required"
    notes: tuple[str, ...] = ()


# ── Tolerance config ──

# Fields where a small diff is acceptable (analyst rounding, timestamp differences)
TOLERANCE_CFG: dict[str, float] = {
    "breadth.turnover_yi": 0.05,        # 5% turnover diff ok (analyst rounds)
    "breadth.up_ratio": 0.02,           # 2% ratio diff
    "capital.total_turnover_yi": 0.05,
    "capital.active_limitup_amount_yi": 0.15,  # 15% — estimates vary
    "limitup.total_count": 0.0,         # 涨停数必须精确
    "limitup.sealed_count": 0.05,       # 5% — ST/20cm threshold variance
    "_default": 0.03,                   # 3% default tolerance
}


# ── Snapshot freezer ──

class MetricsValidator:
    """Freeze MarketMetricsSnapshot and compare against analyst PDF."""

    @staticmethod
    def freeze(snapshot: MarketMetricsSnapshot) -> dict[str, Any]:
        """Serialize snapshot to immutable JSON representation."""
        return {
            "version": "1.1",
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "trade_date": snapshot.trade_date.isoformat(),
            "calibration_applied": snapshot.calibration_applied,
            "calibration_source": snapshot.calibration_source,
            "data_quality_score": snapshot.data_quality_score,
            "breadth": {
                "up_count": snapshot.breadth.up_count,
                "down_count": snapshot.breadth.down_count,
                "limit_up_count": snapshot.breadth.limit_up_count,
                "limit_down_count": snapshot.breadth.limit_down_count,
                "up_ratio": snapshot.breadth.up_ratio,
                "turnover_yi": snapshot.breadth.turnover_yi,
                "source": snapshot.breadth.source.source_type,
            },
            "limitup": {
                "total_count": snapshot.limitup.total_count,
                "sealed_count": snapshot.limitup.sealed_count,
                "fried_board_count": snapshot.limitup.fried_board_count,
                "sealed_board_ratio": snapshot.limitup.sealed_board_ratio,
                "chain_board_count": snapshot.limitup.chain_board_count,
                "max_board_height": snapshot.limitup.max_board_height,
                "max_turnover_board_height": snapshot.limitup.max_turnover_board_height,
                "first_board_count": snapshot.limitup.first_board_count,
                "high_board_count": snapshot.limitup.high_board_count,
                "avg_turnover_rate": snapshot.limitup.avg_turnover_rate,
                "avg_amount_yi": snapshot.limitup.avg_amount_yi,
                "avg_big_order_net_yi": snapshot.limitup.avg_big_order_net_yi,
                "fried_amount_ratio": snapshot.limitup.fried_amount_ratio,
                "board_type_counts": snapshot.limitup.board_type_counts,
                "source": snapshot.limitup.source.source_type,
            },
            "relay": {
                "promotion_1_to_2": snapshot.relay.promotion_1_to_2,
                "promotion_2_to_3": snapshot.relay.promotion_2_to_3,
                "promotion_3_to_4": snapshot.relay.promotion_3_to_4,
                "chain_board_count": snapshot.relay.chain_board_count,
                "max_board_height": snapshot.relay.max_board_height,
                "max_turnover_board_height": snapshot.relay.max_turnover_board_height,
            },
            "capital": {
                "total_turnover_yi": snapshot.capital.total_turnover_yi,
                "active_limitup_amount_yi": snapshot.capital.active_limitup_amount_yi,
                "active_ratio": snapshot.capital.active_ratio,
            },
            "emotion_momentum": {
                "momentum_raw": snapshot.emotion_momentum.momentum_raw,
                "momentum_normalized": snapshot.emotion_momentum.momentum_normalized,
                "first_board_red_ratio": snapshot.emotion_momentum.first_board_red_ratio,
                "first_board_big_loss_ratio": snapshot.emotion_momentum.first_board_big_loss_ratio,
                "chain_board_red_ratio": snapshot.emotion_momentum.chain_board_red_ratio,
                "chain_board_ratio": snapshot.emotion_momentum.chain_board_ratio,
            },
        }

    @staticmethod
    def compare(snapshot: MarketMetricsSnapshot,
                analyst_pdf: dict[str, Any] | None = None) -> ValidationReport:
        """Compare system snapshot against analyst PDF reference.

        Args:
            snapshot: frozen MarketMetricsSnapshot
            analyst_pdf: pre-parsed analyst PDF metrics dict
                         e.g. {"lu": 33, "turnover": 2.56, "emotion": "情绪退潮"}
        """
        diffs: list[MetricDiff] = []

        # ── Extract system values ──
        system_values: dict[str, float | int | None] = {
            "limitup.total_count": snapshot.limitup.total_count,
            "limitup.sealed_count": snapshot.limitup.sealed_count,
            "limitup.fried_board_count": snapshot.limitup.fried_board_count,
            "limitup.sealed_board_ratio": round(snapshot.limitup.sealed_board_ratio, 2),
            "limitup.chain_board_count": snapshot.limitup.chain_board_count,
            "limitup.max_board_height": snapshot.limitup.max_board_height,
            "breadth.turnover_yi": snapshot.breadth.turnover_yi,
            "breadth.up_ratio": snapshot.breadth.up_ratio,
            "capital.total_turnover_yi": snapshot.capital.total_turnover_yi,
            "capital.active_ratio": snapshot.capital.active_ratio,
        }

        # ── Extract analyst values ──
        analyst = analyst_pdf or {}
        analyst_values: dict[str, float | int | None] = {}
        if analyst.get("lu"):
            analyst_values["limitup.total_count"] = int(analyst["lu"])
        if analyst.get("turnover"):
            # PDF turnover is 万亿; convert to 亿 for comparison
            analyst_values["breadth.turnover_yi"] = round(float(analyst["turnover"]) * 10_000)
            analyst_values["capital.total_turnover_yi"] = round(float(analyst["turnover"]) * 10_000)

        # ── Compare ──
        for metric_name, sys_val in system_values.items():
            ana_val = analyst_values.get(metric_name)

            if ana_val is None:
                diffs.append(MetricDiff(
                    metric_name=metric_name, system_value=sys_val,
                    analyst_value=None, absolute_diff=None, relative_diff_pct=None,
                    status="missing_analyst",
                ))
            elif sys_val is None:
                diffs.append(MetricDiff(
                    metric_name=metric_name, system_value=None,
                    analyst_value=ana_val, absolute_diff=None, relative_diff_pct=None,
                    status="missing_system",
                ))
            else:
                abs_diff = abs(float(sys_val) - float(ana_val))
                rel_pct = round(abs_diff / max(abs(float(ana_val)), 0.001) * 100, 1)
                tolerance = TOLERANCE_CFG.get(metric_name, TOLERANCE_CFG["_default"])
                max_abs = max(abs(float(sys_val)), abs(float(ana_val)))

                if abs_diff < 0.001 or (max_abs > 0 and abs_diff / max_abs <= tolerance):
                    status = "match" if abs_diff < 0.001 else "within_tolerance"
                else:
                    status = "diverged"

                diffs.append(MetricDiff(
                    metric_name=metric_name, system_value=sys_val,
                    analyst_value=ana_val, absolute_diff=abs_diff,
                    relative_diff_pct=rel_pct, status=status,
                ))

        match_count = sum(1 for d in diffs if d.status in ("match", "within_tolerance"))
        diverged_count = sum(1 for d in diffs if d.status == "diverged")
        missing_ana = sum(1 for d in diffs if d.status == "missing_analyst")
        missing_sys = sum(1 for d in diffs if d.status == "missing_system")

        if diverged_count == 0:
            overall = "ok"
            notes = ("All metrics match within tolerance.",)
        elif diverged_count <= 2:
            overall = "tolerable"
            notes = (f"{diverged_count} metric(s) diverged — review before trusting diagnosis.",)
        else:
            overall = "review_required"
            notes = (f"{diverged_count} metric(s) significantly diverged — DO NOT use for trading decisions.",)

        return ValidationReport(
            trade_date=snapshot.trade_date,
            generated_at=datetime.now(timezone.utc),
            snapshot_version="1.1",
            snapshot_frozen=True,
            diffs=tuple(diffs),
            match_count=match_count,
            diverged_count=diverged_count,
            missing_analyst_count=missing_ana,
            missing_system_count=missing_sys,
            overall_status=overall,
            notes=notes,
        )

    @staticmethod
    async def save_to_db(conn, snapshot: MarketMetricsSnapshot, report: ValidationReport) -> int:
        """Persist frozen snapshot + validation report to DB. Returns snapshot id."""
        frozen = MetricsValidator.freeze(snapshot)
        row = await conn.fetchrow(
            """INSERT INTO market_metrics_validation_snapshot (
                 trade_date, snapshot_json, report_json, version, overall_status
               ) VALUES ($1, $2::jsonb, $3::jsonb, $4, $5)
               ON CONFLICT (trade_date, version) DO UPDATE SET
                 snapshot_json = EXCLUDED.snapshot_json,
                 report_json = EXCLUDED.report_json,
                 overall_status = EXCLUDED.overall_status,
                 updated_at = NOW()
               RETURNING id""",
            snapshot.trade_date,
            json.dumps(frozen, default=str),
            json.dumps(_report_to_dict(report), default=str),
            "1.1",
            report.overall_status,
        )
        return int(row["id"]) if row else 0


def _report_to_dict(report: ValidationReport) -> dict:
    return {
        "trade_date": report.trade_date.isoformat(),
        "generated_at": report.generated_at.isoformat(),
        "snapshot_version": report.snapshot_version,
        "snapshot_frozen": report.snapshot_frozen,
        "match_count": report.match_count,
        "diverged_count": report.diverged_count,
        "missing_analyst_count": report.missing_analyst_count,
        "missing_system_count": report.missing_system_count,
        "overall_status": report.overall_status,
        "notes": list(report.notes),
        "diffs": [{
            "metric_name": d.metric_name,
            "system_value": d.system_value,
            "analyst_value": d.analyst_value,
            "absolute_diff": d.absolute_diff,
            "relative_diff_pct": d.relative_diff_pct,
            "status": d.status,
        } for d in report.diffs],
    }
